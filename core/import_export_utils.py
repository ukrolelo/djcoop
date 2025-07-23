import os
import json
import zipfile
import tempfile
import shutil
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional

from django.conf import settings
from django.core import serializers
from django.core.files.base import ContentFile
from django.apps import apps
from django.db import models, transaction, connection
from django.contrib.auth.models import User
from django.utils import timezone

from .models import ImportExportOperation, ImportExportLog

# Set up logging
logger = logging.getLogger(__name__)


class ImportExportManager:
    """Main class for handling database and media backup/restore operations"""

    # Define which apps and models to include in database backup
    EXPORTABLE_APPS = {
        'djsql': ['DatabaseServer', 'DatabaseUser'],
        'djmail': ['EmailAccount', 'EmailFolder', 'Email', 'EmailAttachment', 'Task', 'EmailTemplate', 'EmailLog'],
        'djnote': ['Scan', 'ScanPage'],
        'auth': ['User', 'Group'],  # Include user data
        'core': ['ImportExportOperation', 'ImportExportLog']  # Include for completeness
    }

    # Media directories to backup
    MEDIA_DIRECTORIES = [
        'scans',              # djnote scan images
        'email_attachments',  # djmail attachments
        # Note: 'exports' and 'imports' are excluded to avoid recursive backups
    ]
    
    def __init__(self, operation: ImportExportOperation):
        self.operation = operation
        self.temp_dir = None

    def _ensure_db_connection(self):
        """Ensure database connection is available"""
        try:
            # Test the connection with a simple query
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception as e:
            # Log the error but don't try to fix it - let Django handle it
            logger.warning(f"Database connection issue: {str(e)}")
        
    def _retry_db_operation(self, operation_func, max_retries=3):
        """Retry database operations with exponential backoff"""
        import time

        for attempt in range(max_retries):
            try:
                self._ensure_db_connection()
                return operation_func()
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e

                # Wait with exponential backoff
                wait_time = 0.1 * (2 ** attempt)
                time.sleep(wait_time)
                logger.warning(f"Database operation failed (attempt {attempt + 1}), retrying in {wait_time}s: {str(e)}")

    def log(self, level: str, message: str, details: Dict = None):
        """Add log entry for the operation"""
        def _create_log():
            return ImportExportLog.objects.create(
                operation=self.operation,
                level=level,
                message=message,
                details=details or {}
            )

        try:
            self._retry_db_operation(_create_log)
            # Also log to Django logger
            getattr(logger, level.lower(), logger.info)(f"Operation {self.operation.id}: {message}")
        except Exception as e:
            # Fallback logging if database logging fails
            logger.error(f"Failed to log operation {self.operation.id}: {str(e)}")
            logger.log(getattr(logging, level.upper(), logging.INFO), f"Operation {self.operation.id}: {message}")
    
    def create_export_archive(self, selected_apps: List[str] = None, include_media: bool = True) -> str:
        """Create export archive with database data and media files"""
        try:
            self.operation.start_operation()
            self.log('info', 'Starting database and media backup')

            # Validate selected apps
            if not selected_apps:
                selected_apps = list(self.EXPORTABLE_APPS.keys())

            # Filter out invalid apps
            valid_apps = [app for app in selected_apps if app in self.EXPORTABLE_APPS]
            if not valid_apps:
                raise ValueError("No valid apps selected for export")

            if len(valid_apps) != len(selected_apps):
                invalid_apps = set(selected_apps) - set(valid_apps)
                self.log('warning', f'Ignoring invalid apps: {", ".join(invalid_apps)}')

            self.operation.apps_included = valid_apps
            self.operation.save()

            # Ensure export directory exists
            os.makedirs(os.path.join(str(settings.MEDIA_ROOT), 'exports'), exist_ok=True)
            
            # Create temporary directory
            self.temp_dir = tempfile.mkdtemp()
            export_data = {}
            total_records = 0
            processed_records = 0

            # Count total records first
            for app_name in valid_apps:
                if app_name in self.EXPORTABLE_APPS:
                    for model_name in self.EXPORTABLE_APPS[app_name]:
                        try:
                            model = apps.get_model(app_name, model_name)
                            total_records += model.objects.count()
                        except Exception as e:
                            self.log('warning', f'Could not count records for {app_name}.{model_name}: {str(e)}')

            self.operation.update_progress(total_records=total_records)
            self.log('info', f'Found {total_records} database records to export')
            
            # Export database data for each app
            for app_name in valid_apps:
                if app_name not in self.EXPORTABLE_APPS:
                    self.log('warning', f'App {app_name} not in exportable apps list')
                    continue

                app_data = {}
                self.log('info', f'Exporting database data from {app_name}')

                for model_name in self.EXPORTABLE_APPS[app_name]:
                    try:
                        self._ensure_db_connection()
                        model = apps.get_model(app_name, model_name)
                        queryset = model.objects.all()

                        # Serialize model data using Django ORM
                        serialized_data = serializers.serialize('json', queryset)
                        app_data[model_name] = json.loads(serialized_data)

                        processed_records += queryset.count()

                        # Update progress with retry mechanism
                        def _update_progress():
                            self.operation.update_progress(processed_records=processed_records)

                        self._retry_db_operation(_update_progress)

                        self.log('info', f'Exported {queryset.count()} records from {app_name}.{model_name}')

                    except Exception as e:
                        self.log('error', f'Error exporting {app_name}.{model_name}: {str(e)}')
                        continue

                export_data[app_name] = app_data

            # Collect media files if requested
            media_files_info = []
            if include_media:
                self.log('info', 'Collecting media files for backup')
                media_files_info = self._collect_media_directories()

            # Create export metadata
            metadata = {
                'export_date': timezone.now().isoformat(),
                'django_version': getattr(settings, 'DJANGO_VERSION', 'unknown'),
                'apps_included': valid_apps,
                'total_records': total_records,
                'media_files_count': len(media_files_info),
                'include_media': include_media,
                'media_directories': self.MEDIA_DIRECTORIES if include_media else [],
                'exported_by': self.operation.user.username
            }
            
            # Create archive
            archive_path = self._create_zip_archive(export_data, media_files_info, metadata)
            
            # Update operation with retry mechanism
            def _complete_operation():
                # Refresh operation from database first
                self.operation.refresh_from_db()

                # Update all completion information at once
                self.operation.filename = os.path.basename(archive_path)
                self.operation.file_path = archive_path
                self.operation.file_size = os.path.getsize(archive_path)
                self.operation.status = 'completed'
                self.operation.completed_at = timezone.now()
                self.operation.progress_percentage = 100.0

                # Save all fields at once
                self.operation.save(update_fields=[
                    'filename', 'file_path', 'file_size',
                    'status', 'completed_at', 'progress_percentage'
                ])

            self._retry_db_operation(_complete_operation)
            
            self.log('info', f'Export completed successfully. Archive: {archive_path}')
            return archive_path
            
        except Exception as e:
            self.log('error', f'Export failed: {str(e)}')
            self.operation.fail_operation(str(e))
            raise
        finally:
            # Cleanup temp directory
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)

    def _collect_media_directories(self) -> List[Dict]:
        """Collect all files from media directories for backup"""
        media_files = []

        for media_dir in self.MEDIA_DIRECTORIES:
            media_path = os.path.join(str(settings.MEDIA_ROOT), media_dir)

            if not os.path.exists(media_path):
                self.log('info', f'Media directory {media_dir} does not exist, skipping')
                continue

            self.log('info', f'Collecting files from media directory: {media_dir}')

            # Walk through directory and collect all files
            for root, dirs, files in os.walk(media_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    relative_path = os.path.relpath(file_path, str(settings.MEDIA_ROOT))

                    try:
                        file_size = os.path.getsize(file_path)
                        media_files.append({
                            'relative_path': relative_path,
                            'absolute_path': file_path,
                            'size': file_size,
                            'directory': media_dir
                        })
                    except OSError as e:
                        self.log('warning', f'Could not access file {relative_path}: {str(e)}')

            files_count = len([f for f in media_files if f['directory'] == media_dir])
            self.log('info', f'Found {files_count} files in {media_dir}')

        total_size = sum(f['size'] for f in media_files)
        self.log('info', f'Total media files: {len(media_files)}, Total size: {total_size / 1024 / 1024:.2f} MB')

        return media_files

    def _collect_media_files(self, model: models.Model, queryset) -> List[Dict]:
        """Collect media files from model instances"""
        media_files = []
        
        # Find FileField and ImageField fields
        file_fields = []
        for field in model._meta.fields:
            if isinstance(field, (models.FileField, models.ImageField)):
                file_fields.append(field.name)
        
        for instance in queryset:
            for field_name in file_fields:
                file_field = getattr(instance, field_name)
                if file_field and hasattr(file_field, 'path'):
                    try:
                        if os.path.exists(file_field.path):
                            media_files.append({
                                'model': f"{model._meta.app_label}.{model._meta.model_name}",
                                'instance_pk': str(instance.pk),
                                'field_name': field_name,
                                'file_path': file_field.name,  # Relative path
                                'original_path': file_field.path  # Absolute path
                            })
                    except (ValueError, OSError):
                        # File doesn't exist or path is invalid
                        continue
        
        return media_files
    
    def _create_zip_archive(self, export_data: Dict, media_files: List[Dict], metadata: Dict) -> str:
        """Create ZIP archive with database data and media files"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        archive_name = f"djcoop_backup_{timestamp}.zip"
        archive_path = os.path.join(str(settings.MEDIA_ROOT), 'exports', archive_name)

        # Ensure exports directory exists
        os.makedirs(os.path.dirname(archive_path), exist_ok=True)

        self.log('info', f'Creating backup archive: {archive_name}')

        with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Add metadata
            zipf.writestr('backup_metadata.json', json.dumps(metadata, indent=2))
            self.log('info', 'Added metadata to archive')

            # Add database data
            zipf.writestr('database_data.json', json.dumps(export_data, indent=2))
            self.log('info', 'Added database data to archive')

            # Add media files
            media_manifest = []
            added_files = 0

            for media_file in media_files:
                try:
                    if os.path.exists(media_file['absolute_path']):
                        # Add file to archive preserving directory structure
                        archive_path_in_zip = f"media/{media_file['relative_path']}"
                        zipf.write(media_file['absolute_path'], archive_path_in_zip)

                        media_manifest.append({
                            'relative_path': media_file['relative_path'],
                            'archive_path': archive_path_in_zip,
                            'size': media_file['size'],
                            'directory': media_file['directory']
                        })
                        added_files += 1

                        if added_files % 100 == 0:  # Log progress every 100 files
                            self.log('info', f'Added {added_files} media files to archive')

                except Exception as e:
                    self.log('warning', f'Could not add media file {media_file["relative_path"]}: {str(e)}')

            # Add media manifest
            zipf.writestr('media_manifest.json', json.dumps(media_manifest, indent=2))
            self.log('info', f'Added {added_files} media files to archive')

        archive_size = os.path.getsize(archive_path)
        self.log('info', f'Backup archive created: {archive_size / 1024 / 1024:.2f} MB')

        return archive_path

    def validate_import_archive(self, archive_path: str) -> Dict[str, Any]:
        """Validate backup archive and return validation results"""
        try:
            self.log('info', 'Starting backup validation')
            validation_results = {
                'valid': False,
                'errors': [],
                'warnings': [],
                'metadata': {},
                'data_summary': {},
                'conflicts': [],
                'media_files': []
            }

            if not os.path.exists(archive_path):
                validation_results['errors'].append('Backup file does not exist')
                return validation_results

            with zipfile.ZipFile(archive_path, 'r') as zipf:
                # Check required files - support both old and new formats
                metadata_file = None
                data_file = None

                if 'backup_metadata.json' in zipf.namelist():
                    metadata_file = 'backup_metadata.json'
                elif 'metadata.json' in zipf.namelist():
                    metadata_file = 'metadata.json'
                else:
                    validation_results['errors'].append('Missing metadata file')

                if 'database_data.json' in zipf.namelist():
                    data_file = 'database_data.json'
                elif 'data.json' in zipf.namelist():
                    data_file = 'data.json'
                else:
                    validation_results['errors'].append('Missing database data file')

                if validation_results['errors']:
                    return validation_results

                # Read and validate metadata
                try:
                    metadata_content = zipf.read(metadata_file).decode('utf-8')
                    metadata = json.loads(metadata_content)
                    validation_results['metadata'] = metadata

                    # Check if apps exist
                    for app_name in metadata.get('apps_included', []):
                        if app_name not in self.EXPORTABLE_APPS:
                            validation_results['warnings'].append(f'App {app_name} not recognized')

                    # Check backup type
                    if metadata.get('include_media', False):
                        self.log('info', 'Backup includes media files')
                    else:
                        self.log('info', 'Backup contains database data only')

                except Exception as e:
                    validation_results['errors'].append(f'Invalid metadata file: {str(e)}')
                    return validation_results

                # Read and validate database data
                try:
                    data_content = zipf.read(data_file).decode('utf-8')
                    data = json.loads(data_content)

                    # Analyze data and detect conflicts
                    conflicts = self._detect_data_conflicts(data)
                    validation_results['conflicts'] = conflicts
                    validation_results['data_summary'] = self._summarize_data(data)

                    if conflicts:
                        validation_results['warnings'].append(f'Found {len(conflicts)} potential conflicts')

                except Exception as e:
                    validation_results['errors'].append(f'Invalid database data file: {str(e)}')
                    return validation_results

                # Check media files
                if 'media_manifest.json' in zipf.namelist():
                    try:
                        media_content = zipf.read('media_manifest.json').decode('utf-8')
                        media_manifest = json.loads(media_content)
                        validation_results['media_files'] = media_manifest

                        # Verify media files exist in archive
                        missing_media = []
                        for media_file in media_manifest:
                            if media_file['archive_path'] not in zipf.namelist():
                                missing_media.append(media_file['archive_path'])

                        if missing_media:
                            validation_results['warnings'].append(f'Missing {len(missing_media)} media files')

                    except Exception as e:
                        validation_results['warnings'].append(f'Could not read media manifest: {str(e)}')

            # If no errors, mark as valid
            if not validation_results['errors']:
                validation_results['valid'] = True
                self.log('info', 'Import validation completed successfully')
            else:
                self.log('error', f'Import validation failed: {validation_results["errors"]}')

            return validation_results

        except Exception as e:
            self.log('error', f'Import validation error: {str(e)}')
            return {
                'valid': False,
                'errors': [f'Validation error: {str(e)}'],
                'warnings': [],
                'metadata': {},
                'data_summary': {},
                'conflicts': [],
                'media_files': []
            }

    def _detect_data_conflicts(self, data: Dict) -> List[Dict]:
        """Detect potential conflicts with existing data"""
        conflicts = []

        for app_name, app_data in data.items():
            if app_name not in self.EXPORTABLE_APPS:
                continue

            for model_name, model_data in app_data.items():
                try:
                    model = apps.get_model(app_name, model_name)

                    for record in model_data:
                        pk = record['pk']

                        # Check if record with same PK exists
                        if model.objects.filter(pk=pk).exists():
                            existing_obj = model.objects.get(pk=pk)
                            conflicts.append({
                                'model': f'{app_name}.{model_name}',
                                'pk': pk,
                                'type': 'pk_conflict',
                                'message': f'Record with PK {pk} already exists',
                                'existing_data': self._serialize_instance(existing_obj),
                                'import_data': record
                            })

                        # Check for unique field conflicts
                        unique_conflicts = self._check_unique_constraints(model, record)
                        conflicts.extend(unique_conflicts)

                except Exception as e:
                    self.log('warning', f'Could not check conflicts for {app_name}.{model_name}: {str(e)}')

        return conflicts

    def _check_unique_constraints(self, model: models.Model, record: Dict) -> List[Dict]:
        """Check for unique constraint violations"""
        conflicts = []
        fields = record['fields']

        # Check unique fields
        for field in model._meta.fields:
            if field.unique and field.name in fields:
                value = fields[field.name]
                if value and model.objects.filter(**{field.name: value}).exists():
                    conflicts.append({
                        'model': f'{model._meta.app_label}.{model._meta.model_name}',
                        'pk': record['pk'],
                        'type': 'unique_constraint',
                        'field': field.name,
                        'value': value,
                        'message': f'Value "{value}" for field "{field.name}" already exists'
                    })

        return conflicts

    def _serialize_instance(self, instance) -> Dict:
        """Serialize a model instance for comparison"""
        try:
            serialized = serializers.serialize('json', [instance])
            return json.loads(serialized)[0]
        except Exception:
            return {'error': 'Could not serialize instance'}

    def _summarize_data(self, data: Dict) -> Dict:
        """Create summary of data to be imported"""
        summary = {}

        for app_name, app_data in data.items():
            app_summary = {}
            for model_name, model_data in app_data.items():
                app_summary[model_name] = len(model_data)
            summary[app_name] = app_summary

        return summary

    def perform_import(self, archive_path: str, user_selections: Dict = None) -> bool:
        """Perform the actual restore operation"""
        try:
            self.operation.start_operation()
            self.log('info', 'Starting backup restore operation')

            # Store user selections
            if user_selections:
                self.operation.user_selections = user_selections
                self.operation.save()

            with zipfile.ZipFile(archive_path, 'r') as zipf:
                # Determine file names (support both old and new formats)
                data_file = 'database_data.json' if 'database_data.json' in zipf.namelist() else 'data.json'

                # Read database data
                data_content = zipf.read(data_file).decode('utf-8')
                data = json.loads(data_content)
                self.log('info', 'Loaded database data from backup')

                # Read media manifest if exists
                media_manifest = []
                if 'media_manifest.json' in zipf.namelist():
                    media_content = zipf.read('media_manifest.json').decode('utf-8')
                    media_manifest = json.loads(media_content)
                    self.log('info', f'Found {len(media_manifest)} media files in backup')

                # Restore media files if present
                if media_manifest:
                    self.log('info', 'Restoring media files')
                    self._restore_media_files_from_backup(zipf, media_manifest)

                # Count total records
                total_records = sum(len(model_data) for app_data in data.values() for model_data in app_data.values())
                self.operation.update_progress(total_records=total_records)

                # Import database data with smaller transactions per model
                processed_records = 0

                for app_name, app_data in data.items():
                    if app_name not in self.EXPORTABLE_APPS:
                        continue

                    logger.info(f'Restoring database data for {app_name}')

                    for model_name, model_data in app_data.items():
                        try:
                            model = apps.get_model(app_name, model_name)
                            model_processed = 0

                            # Use separate transaction for each model to avoid rollback issues
                            with transaction.atomic():
                                for record in model_data:
                                    try:
                                        # Handle conflicts based on user selections
                                        conflict_resolution = user_selections.get('conflicts', {}).get(
                                            f"{app_name}.{model_name}:{record['pk']}", 'skip'
                                        )

                                        if conflict_resolution == 'skip':
                                            if model.objects.filter(pk=record['pk']).exists():
                                                model_processed += 1
                                                continue
                                        elif conflict_resolution == 'overwrite':
                                            # Delete existing record
                                            model.objects.filter(pk=record['pk']).delete()

                                        # Deserialize and save
                                        record_json = json.dumps([record])
                                        for obj in serializers.deserialize('json', record_json):
                                            obj.save()

                                        model_processed += 1

                                    except Exception as e:
                                        # Log error but continue with other records
                                        logger.error(f'Error restoring record {record["pk"]}: {str(e)}')
                                        continue

                            processed_records += model_processed
                            logger.info(f'Restored {model_processed} records for {app_name}.{model_name}')

                        except Exception as e:
                            logger.error(f'Error restoring {app_name}.{model_name}: {str(e)}')
                            continue

                # Update final progress outside transaction
                self.operation.update_progress(processed_records=processed_records)
                self.operation.complete_operation()
                self.log('info', 'Backup restore completed successfully')
                return True

        except Exception as e:
            self.log('error', f'Backup restore failed: {str(e)}')
            self.operation.fail_operation(str(e))
            return False
        finally:
            # Cleanup temp directory
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)

    def _restore_media_files_from_backup(self, zipf: zipfile.ZipFile, media_manifest: List[Dict]):
        """Restore media files from backup archive"""
        restored_files = 0
        failed_files = 0

        for media_file in media_manifest:
            try:
                archive_path = media_file['archive_path']
                relative_path = media_file['relative_path']
                target_path = os.path.join(str(settings.MEDIA_ROOT), relative_path)

                # Ensure target directory exists
                os.makedirs(os.path.dirname(target_path), exist_ok=True)

                # Extract file directly to target location
                with zipf.open(archive_path) as source:
                    with open(target_path, 'wb') as target:
                        shutil.copyfileobj(source, target)

                restored_files += 1

                if restored_files % 100 == 0:  # Log progress every 100 files
                    self.log('info', f'Restored {restored_files} media files')

            except Exception as e:
                failed_files += 1
                self.log('warning', f'Could not restore media file {media_file["relative_path"]}: {str(e)}')

        self.log('info', f'Media restore completed: {restored_files} files restored, {failed_files} failed')

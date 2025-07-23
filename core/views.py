import os
import json
import threading
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse, Http404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.core.files.storage import default_storage
from django.utils import timezone

from .models import ImportExportOperation
from .import_export_utils import ImportExportManager


def dashboard(request):
    return render(request, 'core/dashboard.html', {
        'title': 'Dashboard',
        'active_menu': 'dashboard'
    })


@login_required
def settings_view(request):
    # Get recent import/export operations for the user
    recent_operations = ImportExportOperation.objects.filter(
        user=request.user
    ).order_by('-created_at')[:10]

    return render(request, 'core/settings.html', {
        'title': 'Settings',
        'active_menu': 'settings',
        'recent_operations': recent_operations,
        'exportable_apps': ImportExportManager.EXPORTABLE_APPS
    })


@login_required
@require_POST
def start_export(request):
    """Start backup operation"""
    try:
        # Get selected apps from request
        selected_apps = request.POST.getlist('apps')
        if not selected_apps:
            return JsonResponse({
                'success': False,
                'error': 'No apps selected for backup'
            })

        # Get include_media option
        include_media = request.POST.get('include_media', 'true').lower() == 'true'

        # Create operation record
        operation = ImportExportOperation.objects.create(
            user=request.user,
            operation_type='export',
            apps_included=selected_apps
        )

        # Start backup in background thread
        def run_export():
            try:
                from django.db import connection
                # Close the database connection to avoid locks
                connection.close()

                manager = ImportExportManager(operation)
                archive_path = manager.create_export_archive(selected_apps, include_media)

                # Update operation with file info
                operation.refresh_from_db()
                if operation.status == 'completed':
                    # File is ready for download
                    pass

            except Exception as e:
                # Refresh operation from database in case of stale data
                try:
                    operation.refresh_from_db()
                    operation.fail_operation(str(e))
                except Exception:
                    # If we can't update the operation, at least log the error
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Export failed for operation {operation.id}: {str(e)}")

        export_thread = threading.Thread(target=run_export)
        export_thread.daemon = True
        export_thread.start()

        return JsonResponse({
            'success': True,
            'operation_id': str(operation.id),
            'message': 'Backup started successfully'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
def export_status(request, operation_id):
    """Get export operation status"""
    try:
        operation = get_object_or_404(
            ImportExportOperation,
            id=operation_id,
            user=request.user,
            operation_type='export'
        )

        # Refresh from database to get latest data
        operation.refresh_from_db()

        # Debug logging
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Export status for {operation_id}: status={operation.status}, filename={operation.filename}, file_size={operation.file_size}")

        response_data = {
            'success': True,
            'status': operation.status,
            'progress': operation.progress_percentage,
            'processed_records': operation.processed_records,
            'total_records': operation.total_records,
            'error_message': operation.error_message,
            'filename': operation.filename or '',
            'file_size': operation.file_size or 0,
            'created_at': operation.created_at.strftime('%d.%m.%Y %H:%M'),
            'completed_at': operation.completed_at.strftime('%d.%m.%Y %H:%M') if operation.completed_at else None
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
def download_export(request, operation_id):
    """Download export file"""
    try:
        operation = get_object_or_404(
            ImportExportOperation,
            id=operation_id,
            user=request.user,
            operation_type='export',
            status='completed'
        )

        if not operation.file_path or not os.path.exists(operation.file_path):
            raise Http404("Export file not found")

        # Serve file
        with open(operation.file_path, 'rb') as f:
            response = HttpResponse(f.read(), content_type='application/zip')
            response['Content-Disposition'] = f'attachment; filename="{operation.filename}"'
            response['Content-Length'] = operation.file_size
            return response

    except Exception as e:
        messages.error(request, f'Error downloading export: {str(e)}')
        return redirect('core:settings')


@login_required
@require_POST
def upload_import_file(request):
    """Upload and validate import file"""
    try:
        if 'import_file' not in request.FILES:
            return JsonResponse({
                'success': False,
                'error': 'No file uploaded'
            })

        uploaded_file = request.FILES['import_file']

        # Validate file type
        if not uploaded_file.name.endswith('.zip'):
            return JsonResponse({
                'success': False,
                'error': 'Only ZIP files are allowed'
            })

        # Create operation record
        operation = ImportExportOperation.objects.create(
            user=request.user,
            operation_type='import',
            filename=uploaded_file.name,
            file_size=uploaded_file.size
        )

        # Save uploaded file
        import_dir = os.path.join(settings.MEDIA_ROOT, 'imports')
        os.makedirs(import_dir, exist_ok=True)

        file_path = os.path.join(import_dir, f"{operation.id}_{uploaded_file.name}")

        with open(file_path, 'wb') as f:
            for chunk in uploaded_file.chunks():
                f.write(chunk)

        operation.file_path = file_path
        operation.save()

        # Start validation in background
        def run_validation():
            try:
                manager = ImportExportManager(operation)
                validation_results = manager.validate_import_archive(file_path)

                # Update operation with validation results
                operation.refresh_from_db()
                operation.validation_results = validation_results
                operation.conflicts_detected = len(validation_results.get('conflicts', [])) > 0

                if validation_results['valid']:
                    operation.status = 'pending'  # Ready for import
                else:
                    operation.status = 'failed'
                    operation.error_message = '; '.join(validation_results['errors'])

                operation.save()

            except Exception as e:
                try:
                    operation.refresh_from_db()
                    operation.fail_operation(str(e))
                except Exception:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Validation failed for operation {operation.id}: {str(e)}")

        validation_thread = threading.Thread(target=run_validation)
        validation_thread.daemon = True
        validation_thread.start()

        return JsonResponse({
            'success': True,
            'operation_id': str(operation.id),
            'message': 'File uploaded successfully, validation in progress'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
def import_validation_status(request, operation_id):
    """Get import validation status"""
    try:
        operation = get_object_or_404(
            ImportExportOperation,
            id=operation_id,
            user=request.user,
            operation_type='import'
        )

        return JsonResponse({
            'success': True,
            'status': operation.status,
            'validation_results': operation.validation_results,
            'conflicts_detected': operation.conflicts_detected,
            'error_message': operation.error_message,
            'filename': operation.filename
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
@require_POST
def start_import(request, operation_id):
    """Start import operation with user selections"""
    try:
        operation = get_object_or_404(
            ImportExportOperation,
            id=operation_id,
            user=request.user,
            operation_type='import',
            status='pending'
        )

        # Get user selections for conflict resolution
        user_selections = {}
        if request.content_type == 'application/json':
            import json
            user_selections = json.loads(request.body.decode('utf-8'))
        else:
            # Handle form data
            for key, value in request.POST.items():
                if key.startswith('conflict_'):
                    conflict_key = key.replace('conflict_', '')
                    if 'conflicts' not in user_selections:
                        user_selections['conflicts'] = {}
                    user_selections['conflicts'][conflict_key] = value

        # Start import in background
        def run_import():
            try:
                manager = ImportExportManager(operation)
                success = manager.perform_import(operation.file_path, user_selections)

                if not success:
                    # Error details should already be logged
                    pass

            except Exception as e:
                try:
                    operation.refresh_from_db()
                    operation.fail_operation(str(e))
                except Exception:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Import failed for operation {operation.id}: {str(e)}")

        import_thread = threading.Thread(target=run_import)
        import_thread.daemon = True
        import_thread.start()

        return JsonResponse({
            'success': True,
            'message': 'Import started successfully'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
def import_status(request, operation_id):
    """Get import operation status"""
    try:
        operation = get_object_or_404(
            ImportExportOperation,
            id=operation_id,
            user=request.user,
            operation_type='import'
        )

        return JsonResponse({
            'success': True,
            'status': operation.status,
            'progress': operation.progress_percentage,
            'processed_records': operation.processed_records,
            'total_records': operation.total_records,
            'failed_records': operation.failed_records,
            'error_message': operation.error_message,
            'created_at': operation.created_at.strftime('%d.%m.%Y %H:%M'),
            'completed_at': operation.completed_at.strftime('%d.%m.%Y %H:%M') if operation.completed_at else None
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
def operation_logs(request, operation_id):
    """Get operation logs"""
    try:
        operation = get_object_or_404(
            ImportExportOperation,
            id=operation_id,
            user=request.user
        )

        logs = operation.logs.all().order_by('timestamp')
        logs_data = []

        for log in logs:
            logs_data.append({
                'level': log.level,
                'message': log.message,
                'timestamp': log.timestamp.strftime('%d.%m.%Y %H:%M:%S'),
                'details': log.details
            })

        return JsonResponse({
            'success': True,
            'logs': logs_data
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
@require_POST
def cleanup_old_operations(request):
    """Clean up old backup/restore operations and files"""
    try:
        days = int(request.POST.get('days', 30))

        from datetime import timedelta
        cutoff_date = timezone.now() - timedelta(days=days)

        # Find old operations
        old_operations = ImportExportOperation.objects.filter(
            created_at__lt=cutoff_date
        )

        deleted_files = 0
        deleted_operations = 0
        freed_space = 0

        for operation in old_operations:
            try:
                # Delete file if exists
                if operation.file_path and os.path.exists(operation.file_path):
                    file_size = os.path.getsize(operation.file_path)
                    os.remove(operation.file_path)
                    deleted_files += 1
                    freed_space += file_size

                # Delete operation (this will cascade to logs)
                operation.delete()
                deleted_operations += 1

            except Exception as e:
                continue  # Skip problematic operations

        return JsonResponse({
            'success': True,
            'deleted_operations': deleted_operations,
            'deleted_files': deleted_files,
            'freed_space_mb': round(freed_space / 1024 / 1024, 2),
            'message': f'Cleaned up {deleted_operations} operations and {deleted_files} files, freed {round(freed_space / 1024 / 1024, 2)} MB'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

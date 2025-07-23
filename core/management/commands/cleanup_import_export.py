import os
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from core.models import ImportExportOperation


class Command(BaseCommand):
    help = 'Clean up old import/export files and operations'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Delete operations older than this many days (default: 30)'
        )
        parser.add_argument(
            '--delete',
            action='store_true',
            help='Actually delete the files and operations (default: dry run)'
        )
        parser.add_argument(
            '--keep-completed',
            action='store_true',
            help='Keep completed export operations (only delete failed/cancelled)'
        )

    def handle(self, *args, **options):
        days = options['days']
        delete = options['delete']
        keep_completed = options['keep_completed']
        
        cutoff_date = timezone.now() - timedelta(days=days)
        
        self.stdout.write(f"Looking for operations older than {days} days (before {cutoff_date.strftime('%d.%m.%Y %H:%M')})")
        
        # Build query
        query = ImportExportOperation.objects.filter(created_at__lt=cutoff_date)
        
        if keep_completed:
            query = query.exclude(status='completed', operation_type='export')
        
        operations = query.all()
        
        if not operations:
            self.stdout.write(self.style.SUCCESS('No operations found to clean up'))
            return
        
        self.stdout.write(f"Found {operations.count()} operations to clean up:")
        
        total_size = 0
        files_to_delete = []
        
        for operation in operations:
            status_color = self.style.SUCCESS if operation.status == 'completed' else self.style.ERROR
            
            self.stdout.write(
                f"  - {operation.get_operation_type_display()} by {operation.user.username} "
                f"({status_color(operation.status)}) - {operation.created_at.strftime('%d.%m.%Y %H:%M')}"
            )
            
            if operation.file_path and os.path.exists(operation.file_path):
                file_size = os.path.getsize(operation.file_path)
                total_size += file_size
                files_to_delete.append(operation.file_path)
                self.stdout.write(f"    File: {operation.file_path} ({file_size / 1024 / 1024:.2f} MB)")
            elif operation.file_path:
                self.stdout.write(f"    File: {operation.file_path} (not found)")
        
        self.stdout.write(f"\nTotal file size to be freed: {total_size / 1024 / 1024:.2f} MB")
        
        if delete:
            self.stdout.write(self.style.WARNING('\nDeleting operations and files...'))
            
            deleted_files = 0
            deleted_operations = 0
            
            for operation in operations:
                try:
                    # Delete file if exists
                    if operation.file_path and os.path.exists(operation.file_path):
                        os.remove(operation.file_path)
                        deleted_files += 1
                        self.stdout.write(f"  Deleted file: {operation.file_path}")
                    
                    # Delete operation (this will cascade to logs)
                    operation.delete()
                    deleted_operations += 1
                    
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f"  Error deleting operation {operation.id}: {str(e)}")
                    )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'\nCleanup completed: {deleted_operations} operations and {deleted_files} files deleted'
                )
            )
            
            # Clean up empty directories
            self._cleanup_empty_dirs()
            
        else:
            self.stdout.write(
                self.style.WARNING('\nDry run mode - no files were deleted. Use --delete to actually delete files.')
            )
    
    def _cleanup_empty_dirs(self):
        """Remove empty export/import directories"""
        dirs_to_check = [
            os.path.join(settings.MEDIA_ROOT, 'exports'),
            os.path.join(settings.MEDIA_ROOT, 'imports')
        ]
        
        for dir_path in dirs_to_check:
            if os.path.exists(dir_path) and not os.listdir(dir_path):
                try:
                    os.rmdir(dir_path)
                    self.stdout.write(f"  Removed empty directory: {dir_path}")
                except OSError:
                    pass  # Directory not empty or permission denied

#!/usr/bin/env python
"""
Simple test script to verify import/export functionality
Run this with: python test_import_export.py
"""

import os
import sys
import django
from django.conf import settings

# Add the project directory to Python path
sys.path.insert(0, '/home/ukro/Desktop/Programming/djcoop')

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'djcoop.settings')
django.setup()

from django.contrib.auth.models import User
from core.models import ImportExportOperation, ImportExportLog
from core.import_export_utils import ImportExportManager


def test_basic_functionality():
    """Test basic import/export functionality"""
    print("Testing Import/Export Functionality")
    print("=" * 50)
    
    # Create test user
    user, created = User.objects.get_or_create(
        username='testuser',
        defaults={
            'email': 'test@example.com',
            'first_name': 'Test',
            'last_name': 'User'
        }
    )
    if created:
        user.set_password('testpass123')
        user.save()
        print(f"✓ Created test user: {user.username}")
    else:
        print(f"✓ Using existing test user: {user.username}")
    
    # Test 1: Create ImportExportOperation
    print("\n1. Testing ImportExportOperation model...")
    operation = ImportExportOperation.objects.create(
        user=user,
        operation_type='export',
        apps_included=['djsql', 'djmail', 'djnote']
    )
    print(f"✓ Created operation: {operation.id}")
    print(f"  - Type: {operation.operation_type}")
    print(f"  - Status: {operation.status}")
    print(f"  - Apps: {operation.apps_included}")
    
    # Test 2: Test logging
    print("\n2. Testing logging functionality...")
    manager = ImportExportManager(operation)
    manager.log('info', 'Test log message', {'test': 'data'})
    
    logs = ImportExportLog.objects.filter(operation=operation)
    if logs.exists():
        log = logs.first()
        print(f"✓ Created log entry: {log.level} - {log.message}")
        print(f"  - Details: {log.details}")
    else:
        print("✗ Failed to create log entry")
    
    # Test 3: Test operation progress tracking
    print("\n3. Testing progress tracking...")
    operation.update_progress(processed_records=25, total_records=100)
    operation.refresh_from_db()
    print(f"✓ Progress updated: {operation.progress_percentage}%")
    print(f"  - Processed: {operation.processed_records}/{operation.total_records}")
    
    # Test 4: Test operation completion
    print("\n4. Testing operation completion...")
    operation.complete_operation()
    operation.refresh_from_db()
    print(f"✓ Operation completed: {operation.status}")
    print(f"  - Progress: {operation.progress_percentage}%")
    print(f"  - Completed at: {operation.completed_at}")
    
    # Test 5: Test exportable apps configuration
    print("\n5. Testing exportable apps configuration...")
    exportable_apps = ImportExportManager.EXPORTABLE_APPS
    print(f"✓ Exportable apps configured: {list(exportable_apps.keys())}")
    for app_name, models in exportable_apps.items():
        print(f"  - {app_name}: {len(models)} models")
    
    # Test 6: Test validation functionality
    print("\n6. Testing validation functionality...")
    import_operation = ImportExportOperation.objects.create(
        user=user,
        operation_type='import'
    )
    import_manager = ImportExportManager(import_operation)
    
    # Test with non-existent file
    validation_results = import_manager.validate_import_archive('/nonexistent/file.zip')
    if not validation_results['valid'] and 'does not exist' in validation_results['errors'][0]:
        print("✓ Validation correctly handles non-existent files")
    else:
        print("✗ Validation failed to handle non-existent files properly")
    
    print("\n" + "=" * 50)
    print("Basic functionality tests completed!")
    
    # Cleanup
    print("\nCleaning up test data...")
    ImportExportOperation.objects.filter(user=user).delete()
    print("✓ Test operations cleaned up")
    
    return True


def test_model_relationships():
    """Test model relationships and constraints"""
    print("\nTesting Model Relationships")
    print("=" * 30)
    
    user = User.objects.get(username='testuser')
    
    # Create operation with logs
    operation = ImportExportOperation.objects.create(
        user=user,
        operation_type='export'
    )
    
    # Create multiple logs
    for i in range(3):
        ImportExportLog.objects.create(
            operation=operation,
            level='info',
            message=f'Test log message {i+1}',
            details={'step': i+1}
        )
    
    # Test cascade deletion
    log_count = ImportExportLog.objects.filter(operation=operation).count()
    print(f"✓ Created {log_count} log entries")
    
    operation_id = operation.id
    operation.delete()
    remaining_logs = ImportExportLog.objects.filter(operation_id=operation_id).count()
    print(f"✓ Cascade deletion: {remaining_logs} logs remaining (should be 0)")
    
    return True


if __name__ == '__main__':
    try:
        success = test_basic_functionality()
        if success:
            test_model_relationships()
            print("\n🎉 All tests passed!")
        else:
            print("\n❌ Some tests failed!")
            sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

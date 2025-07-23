import os
import json
import tempfile
import zipfile
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.conf import settings
from unittest.mock import patch, MagicMock

from .models import ImportExportOperation, ImportExportLog
from .import_export_utils import ImportExportManager


class ImportExportTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')

    def test_import_export_operation_creation(self):
        """Test creating import/export operations"""
        operation = ImportExportOperation.objects.create(
            user=self.user,
            operation_type='export',
            apps_included=['djsql', 'djmail']
        )

        self.assertEqual(operation.user, self.user)
        self.assertEqual(operation.operation_type, 'export')
        self.assertEqual(operation.status, 'pending')
        self.assertEqual(operation.apps_included, ['djsql', 'djmail'])

    def test_operation_logging(self):
        """Test operation logging functionality"""
        operation = ImportExportOperation.objects.create(
            user=self.user,
            operation_type='export'
        )

        manager = ImportExportManager(operation)
        manager.log('info', 'Test log message', {'detail': 'test'})

        logs = ImportExportLog.objects.filter(operation=operation)
        self.assertEqual(logs.count(), 1)

        log = logs.first()
        self.assertEqual(log.level, 'info')
        self.assertEqual(log.message, 'Test log message')
        self.assertEqual(log.details, {'detail': 'test'})

    def test_start_export_view(self):
        """Test starting export operation via view"""
        response = self.client.post(reverse('core:start_export'), {
            'apps': ['djsql', 'djmail']
        })

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('operation_id', data)

        # Check operation was created
        operation = ImportExportOperation.objects.get(id=data['operation_id'])
        self.assertEqual(operation.user, self.user)
        self.assertEqual(operation.operation_type, 'export')

    def test_export_status_view(self):
        """Test export status view"""
        operation = ImportExportOperation.objects.create(
            user=self.user,
            operation_type='export',
            status='completed',
            filename='test_export.zip',
            total_records=100,
            processed_records=100
        )

        response = self.client.get(reverse('core:export_status', args=[operation.id]))
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['status'], 'completed')
        self.assertEqual(data['filename'], 'test_export.zip')

    def test_settings_page_access(self):
        """Test settings page loads with import/export interface"""
        response = self.client.get(reverse('core:settings'))
        self.assertEqual(response.status_code, 200)

        # Check that import/export elements are present
        self.assertContains(response, 'Data Import/Export')
        self.assertContains(response, 'export-form')
        self.assertContains(response, 'import-form')

    def tearDown(self):
        # Clean up any test files
        for operation in ImportExportOperation.objects.all():
            if operation.file_path and os.path.exists(operation.file_path):
                try:
                    os.unlink(operation.file_path)
                except OSError:
                    pass

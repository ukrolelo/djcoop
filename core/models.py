from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import uuid


class ImportExportOperation(models.Model):
    """Track import/export operations"""
    OPERATION_TYPES = [
        ('export', 'Export'),
        ('import', 'Import'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='import_export_operations')
    operation_type = models.CharField(max_length=10, choices=OPERATION_TYPES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # File information
    filename = models.CharField(max_length=255, blank=True)
    file_path = models.CharField(max_length=500, blank=True)
    file_size = models.BigIntegerField(null=True, blank=True)

    # Operation details
    apps_included = models.JSONField(default=list, help_text="List of apps included in operation")
    total_records = models.IntegerField(default=0)
    processed_records = models.IntegerField(default=0)
    failed_records = models.IntegerField(default=0)

    # Progress and timing
    progress_percentage = models.FloatField(default=0.0)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Error information
    error_message = models.TextField(blank=True)
    error_details = models.JSONField(default=dict, blank=True)

    # Import-specific fields
    validation_results = models.JSONField(default=dict, blank=True)
    conflicts_detected = models.BooleanField(default=False)
    user_selections = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Import/Export Operation'
        verbose_name_plural = 'Import/Export Operations'

    def __str__(self):
        return f"{self.get_operation_type_display()} - {self.status} ({self.created_at.strftime('%d.%m.%Y %H:%M')})"

    def start_operation(self):
        """Mark operation as started"""
        self.status = 'in_progress'
        self.started_at = timezone.now()
        self.save(update_fields=['status', 'started_at'])

    def complete_operation(self):
        """Mark operation as completed"""
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.progress_percentage = 100.0
        self.save(update_fields=['status', 'completed_at', 'progress_percentage'])

    def fail_operation(self, error_message, error_details=None):
        """Mark operation as failed"""
        self.status = 'failed'
        self.error_message = error_message
        if error_details:
            self.error_details = error_details
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'error_message', 'error_details', 'completed_at'])

    def update_progress(self, processed_records=None, total_records=None):
        """Update operation progress"""
        update_fields = []

        if processed_records is not None:
            self.processed_records = processed_records
            update_fields.append('processed_records')
        if total_records is not None:
            self.total_records = total_records
            update_fields.append('total_records')

        if self.total_records > 0:
            self.progress_percentage = (self.processed_records / self.total_records) * 100
            update_fields.append('progress_percentage')

        if update_fields:
            self.save(update_fields=update_fields)


class ImportExportLog(models.Model):
    """Detailed logging for import/export operations"""
    LOG_LEVELS = [
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('error', 'Error'),
        ('debug', 'Debug'),
    ]

    operation = models.ForeignKey(ImportExportOperation, on_delete=models.CASCADE, related_name='logs')
    level = models.CharField(max_length=10, choices=LOG_LEVELS)
    message = models.TextField()
    details = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.level.upper()}: {self.message[:50]}..."

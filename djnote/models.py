from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta


class Scan(models.Model):
    """Main scan model - represents a document or note collection"""
    SCAN_TYPES = [
        ('document', 'Document'),
        ('note', 'Note'),
    ]

    # Using default auto-incrementing integer ID (Django's default)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='scans')
    title = models.CharField(max_length=200)
    scan_type = models.CharField(max_length=20, choices=SCAN_TYPES, default='note')
    document_id = models.CharField(max_length=50, blank=True, null=True, help_text="Auto-generated ID for documents")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Document-specific fields
    retention_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="How many days to keep this document (only for documents)"
    )
    due_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this document should be deleted"
    )

    # General fields
    description = models.TextField(blank=True)
    is_archived = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.get_scan_type_display()})"

    def save(self, *args, **kwargs):
        # Auto-generate document ID for documents
        if self.scan_type == 'document' and not self.document_id:
            # Generate a unique document ID
            last_doc = Scan.objects.filter(
                scan_type='document',
                document_id__isnull=False
            ).order_by('-document_id').first()

            if last_doc and last_doc.document_id.isdigit():
                next_id = int(last_doc.document_id) + 1
            else:
                next_id = 1

            self.document_id = str(next_id).zfill(6)  # 6-digit padded number

        # Calculate due date if retention_days is set and no due_date is manually set
        if self.retention_days and self.scan_type == 'document' and not self.due_date:
            # Use created_at if available, otherwise use current time
            base_date = self.created_at if self.created_at else timezone.now()
            self.due_date = base_date + timedelta(days=self.retention_days)

        super().save(*args, **kwargs)

    @property
    def is_due_soon(self):
        """Check if document is due for deletion within 7 days"""
        if not self.due_date:
            return False
        return self.due_date <= timezone.now() + timedelta(days=7)

    @property
    def is_overdue(self):
        """Check if document is overdue for deletion"""
        if not self.due_date:
            return False
        return self.due_date <= timezone.now()

    @property
    def page_count(self):
        """Get the number of pages in this scan"""
        return self.pages.count()


class ScanPage(models.Model):
    """Individual pages within a scan"""
    # Using default auto-incrementing integer ID (Django's default)
    scan = models.ForeignKey(Scan, on_delete=models.CASCADE, related_name='pages')
    page_number = models.PositiveIntegerField()
    image = models.ImageField(upload_to='scans/%Y/%m/%d/')
    thumbnail = models.ImageField(upload_to='scans/thumbnails/%Y/%m/%d/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Optional OCR text extraction
    extracted_text = models.TextField(blank=True, help_text="OCR extracted text")

    class Meta:
        ordering = ['page_number']
        unique_together = ['scan', 'page_number']

    def __str__(self):
        return f"{self.scan.title} - Page {self.page_number}"

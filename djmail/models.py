from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User

class EmailAccount(models.Model):
    """Model for storing POP3 email account settings"""
    name = models.CharField(max_length=100)
    email = models.EmailField()
    pop3_server = models.CharField(max_length=255)
    pop3_port = models.IntegerField(default=995)
    smtp_server = models.CharField(max_length=255)
    smtp_port = models.IntegerField(default=587)
    username = models.CharField(max_length=255)
    password = models.CharField(max_length=255)
    use_ssl = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.name} ({self.email})"

class EmailFolder(models.Model):
    """Model for email folders"""
    FOLDER_TYPES = (
        ('inbox', 'Inbox'),
        ('sent', 'Sent'),
        ('drafts', 'Drafts'),
        ('trash', 'Trash'),
        ('custom', 'Custom'),
    )
    
    account = models.ForeignKey(EmailAccount, on_delete=models.CASCADE, related_name='folders')
    name = models.CharField(max_length=100)
    folder_type = models.CharField(max_length=20, choices=FOLDER_TYPES, default='custom')
    is_system = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.account.name} - {self.name}"
    
    class Meta:
        unique_together = ('account', 'folder_type')

class Email(models.Model):
    """Model for storing emails"""
    account = models.ForeignKey(EmailAccount, on_delete=models.CASCADE, related_name='emails')
    folder = models.ForeignKey(EmailFolder, on_delete=models.CASCADE, related_name='emails')
    message_id = models.CharField(max_length=255, blank=True, null=True)
    subject = models.CharField(max_length=255, blank=True)
    sender = models.CharField(max_length=255)
    sender_name = models.CharField(max_length=255, blank=True)
    recipients = models.TextField()  # Stores multiple recipients as JSON
    cc = models.TextField(blank=True)  # Stores CC recipients as JSON
    bcc = models.TextField(blank=True)  # Stores BCC recipients as JSON
    body_text = models.TextField(blank=True)
    body_html = models.TextField(blank=True)
    date_received = models.DateTimeField(default=timezone.now)
    read = models.BooleanField(default=False)
    flagged = models.BooleanField(default=False)
    replied = models.BooleanField(default=False)
    forwarded = models.BooleanField(default=False)
    size = models.IntegerField(default=0)  # Size in bytes
    uid = models.CharField(max_length=255, blank=True, null=True)  # Unique ID from the mail server
    
    def __str__(self):
        return f"{self.subject} - {self.sender} ({self.date_received.strftime('%Y-%m-%d %H:%M')})"
    
    class Meta:
        ordering = ['-date_received']

class EmailAttachment(models.Model):
    """Model for email attachments"""
    email = models.ForeignKey(Email, on_delete=models.CASCADE, related_name='attachments')
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    size = models.IntegerField()  # Size in bytes
    file = models.FileField(upload_to='email_attachments/%Y/%m/')
    
    def __str__(self):
        return f"{self.filename} ({self.content_type}, {self.size} bytes)"

class Task(models.Model):
    """Model for tasks that can be linked to emails"""
    STATUS_CHOICES = (
        ('not_started', 'Not Started'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('deferred', 'Deferred'),
    )
    
    PRIORITY_CHOICES = (
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    )
    
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    related_email = models.ForeignKey(Email, on_delete=models.SET_NULL, blank=True, null=True, related_name='tasks')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='not_started')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    due_date = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    
    def __str__(self):
        return self.title
    
    def mark_completed(self):
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.save()

# Keep existing email template and log models
class EmailTemplate(models.Model):
    """Model for storing email templates"""
    name = models.CharField(max_length=100)
    subject = models.CharField(max_length=255)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name

class EmailLog(models.Model):
    """Model for logging sent emails"""
    recipient = models.EmailField()
    subject = models.CharField(max_length=255)
    body = models.TextField()
    template = models.ForeignKey(EmailTemplate, on_delete=models.SET_NULL, null=True, blank=True)
    sent_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(
        max_length=20, 
        choices=[
            ('sent', 'Sent'),
            ('failed', 'Failed'),
            ('pending', 'Pending'),
        ],
        default='pending'
    )
    error_message = models.TextField(null=True, blank=True)
    
    def __str__(self):
        return f"Email to {self.recipient} - {self.sent_at.strftime('%Y-%m-%d %H:%M')}"

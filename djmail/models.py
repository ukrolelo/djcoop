from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from djsql.utils import encrypt_data, decrypt_data

# Add helper methods to User model
def get_accessible_email_accounts(self):
    """Get all email accounts this user has access to"""
    if self.is_superuser:
        return EmailAccount.objects.all()
    return EmailAccount.objects.filter(user_accesses__user=self)

def can_access_email_account(self, email_account):
    """Check if user can access a specific email account"""
    if self.is_superuser:
        return True
    return EmailAccountAccess.objects.filter(user=self, email_account=email_account).exists()

def get_email_account_access_level(self, email_account):
    """Get user's access level for a specific email account"""
    if self.is_superuser:
        return 'full'
    try:
        access = EmailAccountAccess.objects.get(user=self, email_account=email_account)
        return access.access_level
    except EmailAccountAccess.DoesNotExist:
        return None

# Monkey patch the User model
User.add_to_class('get_accessible_email_accounts', get_accessible_email_accounts)
User.add_to_class('can_access_email_account', can_access_email_account)
User.add_to_class('get_email_account_access_level', get_email_account_access_level)

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

    def set_password(self, plain_password):
        """Encrypt and set the password"""
        self.password = encrypt_data(plain_password)

    def get_password(self):
        """Decrypt and return the password"""
        return decrypt_data(self.password)

    def get_authorized_users(self):
        """Get all users who have access to this email account"""
        return User.objects.filter(emailaccountaccess__email_account=self)

    def is_accessible_by_user(self, user):
        """Check if a user has access to this email account"""
        if user.is_superuser:
            return True
        return EmailAccountAccess.objects.filter(user=user, email_account=self).exists()

class EmailFolder(models.Model):
    """Model for email folders"""
    FOLDER_TYPES = (
        ('inbox', 'Inbox'),
        ('sent', 'Sent'),
        ('drafts', 'Drafts'),
        ('outbox', 'Outbox'),
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


class EmailServerLog(models.Model):
    """Model to store detailed email server communication logs"""
    LOG_TYPES = [
        ('send', 'Email Sent'),
        ('receive', 'Email Received'),
        ('smtp_connect', 'SMTP Connection'),
        ('smtp_auth', 'SMTP Authentication'),
        ('smtp_command', 'SMTP Command'),
        ('smtp_response', 'SMTP Response'),
        ('smtp_error', 'SMTP Error'),
        ('imap_connect', 'IMAP Connection'),
        ('imap_auth', 'IMAP Authentication'),
        ('imap_command', 'IMAP Command'),
        ('imap_response', 'IMAP Response'),
        ('imap_error', 'IMAP Error'),
        ('system', 'System Log'),
    ]

    STATUS_CHOICES = [
        ('success', 'Success'),
        ('error', 'Error'),
        ('warning', 'Warning'),
        ('info', 'Info'),
    ]

    # Basic log information
    log_type = models.CharField(max_length=20, choices=LOG_TYPES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    timestamp = models.DateTimeField(auto_now_add=True)

    # Email account and user context
    email_account = models.ForeignKey(EmailAccount, on_delete=models.CASCADE, null=True, blank=True, related_name='server_logs')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='email_server_logs')

    # Email details (for sent/received emails)
    email = models.ForeignKey(Email, on_delete=models.CASCADE, null=True, blank=True, related_name='server_logs')
    subject = models.CharField(max_length=255, blank=True)
    from_email = models.EmailField(blank=True)
    to_email = models.TextField(blank=True)  # Can be multiple recipients

    # Server communication details
    server_host = models.CharField(max_length=255, blank=True)
    server_port = models.IntegerField(null=True, blank=True)
    protocol = models.CharField(max_length=10, blank=True)  # SMTP, IMAP, POP3

    # Command and response details
    command = models.TextField(blank=True)  # SMTP/IMAP command sent
    response = models.TextField(blank=True)  # Server response
    response_code = models.CharField(max_length=10, blank=True)  # Response code (e.g., 250, 550)

    # Log message and details
    message = models.TextField()
    details = models.JSONField(default=dict, blank=True)  # Store additional data

    # Performance metrics
    duration_ms = models.IntegerField(null=True, blank=True)  # Duration in milliseconds

    # Error information
    error_code = models.CharField(max_length=50, blank=True)
    error_message = models.TextField(blank=True)

    # Session tracking
    session_id = models.CharField(max_length=100, blank=True)  # Track related operations

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Email Server Log'
        verbose_name_plural = 'Email Server Logs'
        indexes = [
            models.Index(fields=['timestamp']),
            models.Index(fields=['log_type']),
            models.Index(fields=['status']),
            models.Index(fields=['email_account']),
            models.Index(fields=['user']),
            models.Index(fields=['session_id']),
        ]

    def __str__(self):
        return f"{self.get_log_type_display()} - {self.status} - {self.timestamp}"

    @property
    def duration_seconds(self):
        """Return duration in seconds"""
        if self.duration_ms:
            return self.duration_ms / 1000
        return None

class EmailAccountAccess(models.Model):
    """Model for managing user access to email accounts"""
    ACCESS_LEVELS = (
        ('read', 'Read Only'),
        ('full', 'Full Access'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='email_account_accesses')
    email_account = models.ForeignKey(EmailAccount, on_delete=models.CASCADE, related_name='user_accesses')
    access_level = models.CharField(max_length=10, choices=ACCESS_LEVELS, default='read')
    granted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='granted_accesses')
    granted_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, help_text="Optional notes about this access grant")

    class Meta:
        unique_together = ('user', 'email_account')
        verbose_name = "Email Account Access"
        verbose_name_plural = "Email Account Accesses"

    def __str__(self):
        return f"{self.user.username} -> {self.email_account.name} ({self.access_level})"

from django.db import models

class DatabaseServer(models.Model):
    name = models.CharField(max_length=100, unique=True)
    host = models.CharField(max_length=255)
    port = models.IntegerField(default=3306)
    username = models.CharField(max_length=100)
    password = models.CharField(max_length=255) # Reverted to CharField
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.host}:{self.port})"

    class Meta:
        ordering = ['name']
        verbose_name = 'Database Server'
        verbose_name_plural = 'Database Servers'

class DatabaseUser(models.Model):
    USER_TYPE_CHOICES = [
        ('admin', 'Administrator'),
        ('repl', 'Replication User'),
        ('app', 'Application User'),
    ]

    server = models.ForeignKey(DatabaseServer, on_delete=models.CASCADE, related_name='users')
    username = models.CharField(max_length=100)
    password = models.CharField(max_length=255) # Reverted to CharField
    host = models.CharField(max_length=255, default='%')
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES)
    privileges = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.username}@{self.host} on {self.server.name}"

    class Meta:
        ordering = ['server', 'username', 'host']
        unique_together = [['server', 'username', 'host']]
        verbose_name = 'Database User'
        verbose_name_plural = 'Database Users'

class ReplicationLink(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending Setup'),
        ('configuring_source', 'Configuring Source'),
        ('waiting_source_config', 'Waiting for Source Configuration'),
        ('dumping_data', 'Dumping Source Data'),
        ('importing_data', 'Importing to Target'),
        ('configuring_target', 'Configuring Target'),
        ('starting_replication', 'Starting Replication'),
        ('active', 'Active'),
        ('error', 'Error'),
        ('stopped', 'Stopped'),
    ]

    source = models.ForeignKey(DatabaseServer, on_delete=models.CASCADE, related_name='source_replications')
    target = models.ForeignKey(DatabaseServer, on_delete=models.CASCADE, related_name='target_replications')
    databases = models.JSONField(help_text="List of databases to replicate")
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending')
    lag_seconds = models.IntegerField(default=0)
    replication_user = models.CharField(max_length=100, blank=True)
    replication_password = models.CharField(max_length=255, blank=True) # Reverted to CharField
    server_id_source = models.IntegerField(null=True, blank=True)
    server_id_target = models.IntegerField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    setup_step = models.IntegerField(default=1)
    setup_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Replication {self.source.name} → {self.target.name}"

    class Meta:
        unique_together = [['source', 'target']]
        ordering = ['source__name', 'target__name']

class ReplicationSetupLog(models.Model):
    replication = models.ForeignKey(ReplicationLink, on_delete=models.CASCADE, related_name='setup_logs')
    timestamp = models.DateTimeField(auto_now_add=True)
    step = models.IntegerField()
    status = models.CharField(max_length=50)
    message = models.TextField()
    is_error = models.BooleanField(default=False)
    command_to_run = models.TextField(blank=True)
    requires_user_action = models.BooleanField(default=False)
    user_action_completed = models.BooleanField(default=False)

    class Meta:
        ordering = ['-timestamp']

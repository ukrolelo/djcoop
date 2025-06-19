from django.contrib import admin
from .models import (
    EmailTemplate, EmailLog, EmailAccount, 
    EmailFolder, Email, EmailAttachment, Task
)

@admin.register(EmailAccount)
class EmailAccountAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'pop3_server', 'is_default', 'created_at')
    list_filter = ('use_ssl', 'is_default')
    search_fields = ('name', 'email', 'pop3_server')

@admin.register(EmailFolder)
class EmailFolderAdmin(admin.ModelAdmin):
    list_display = ('name', 'account', 'folder_type', 'is_system')
    list_filter = ('folder_type', 'is_system')
    search_fields = ('name', 'account__name')

@admin.register(Email)
class EmailAdmin(admin.ModelAdmin):
    list_display = ('subject', 'sender', 'account', 'folder', 'date_received', 'read')
    list_filter = ('read', 'flagged', 'replied', 'forwarded', 'folder__folder_type')
    search_fields = ('subject', 'sender', 'body_text', 'recipients')
    date_hierarchy = 'date_received'

@admin.register(EmailAttachment)
class EmailAttachmentAdmin(admin.ModelAdmin):
    list_display = ('filename', 'content_type', 'size', 'email')
    list_filter = ('content_type',)
    search_fields = ('filename', 'email__subject')

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'status', 'priority', 'due_date', 'created_at')
    list_filter = ('status', 'priority')
    search_fields = ('title', 'description')
    date_hierarchy = 'created_at'

@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'subject', 'created_at', 'updated_at')
    search_fields = ('name', 'subject', 'body')

@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'subject', 'status', 'sent_at')
    list_filter = ('status',)
    search_fields = ('recipient', 'subject', 'body')
    date_hierarchy = 'sent_at'

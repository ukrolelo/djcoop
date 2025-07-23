from django.contrib import admin

from .models import ImportExportOperation, ImportExportLog


@admin.register(ImportExportOperation)
class ImportExportOperationAdmin(admin.ModelAdmin):
    list_display = ('operation_type', 'user', 'status', 'filename', 'progress_percentage', 'created_at', 'completed_at')
    list_filter = ('operation_type', 'status', 'created_at', 'apps_included')
    search_fields = ('user__username', 'filename', 'error_message')
    readonly_fields = ('id', 'created_at', 'started_at', 'completed_at', 'progress_percentage', 'validation_results')

    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'user', 'operation_type', 'status')
        }),
        ('File Information', {
            'fields': ('filename', 'file_path', 'file_size')
        }),
        ('Operation Details', {
            'fields': ('apps_included', 'total_records', 'processed_records', 'failed_records', 'progress_percentage')
        }),
        ('Timing', {
            'fields': ('created_at', 'started_at', 'completed_at')
        }),
        ('Error Information', {
            'fields': ('error_message', 'error_details'),
            'classes': ('collapse',)
        }),
        ('Import Specific', {
            'fields': ('validation_results', 'conflicts_detected', 'user_selections'),
            'classes': ('collapse',)
        })
    )

    def has_add_permission(self, request):
        return False  # Operations are created programmatically

    def has_change_permission(self, request, obj=None):
        return False  # Operations should not be manually modified


@admin.register(ImportExportLog)
class ImportExportLogAdmin(admin.ModelAdmin):
    list_display = ('operation', 'level', 'message_preview', 'timestamp')
    list_filter = ('level', 'timestamp', 'operation__operation_type')
    search_fields = ('message', 'operation__user__username')
    readonly_fields = ('operation', 'level', 'message', 'details', 'timestamp')

    def message_preview(self, obj):
        return obj.message[:100] + '...' if len(obj.message) > 100 else obj.message
    message_preview.short_description = 'Message'

    def has_add_permission(self, request):
        return False  # Logs are created programmatically

    def has_change_permission(self, request, obj=None):
        return False  # Logs should not be manually modified

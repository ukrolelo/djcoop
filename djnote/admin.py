from django.contrib import admin
from django.utils.html import format_html
from .models import Scan, ScanPage


class ScanPageInline(admin.TabularInline):
    model = ScanPage
    extra = 0
    readonly_fields = ['thumbnail_preview', 'created_at']
    fields = ['page_number', 'image', 'thumbnail_preview', 'created_at']

    def thumbnail_preview(self, obj):
        if obj.thumbnail:
            return format_html(
                '<img src="{}" style="max-height: 50px; max-width: 50px;" />',
                obj.thumbnail.url
            )
        return "No thumbnail"
    thumbnail_preview.short_description = "Thumbnail"


@admin.register(Scan)
class ScanAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'scan_type', 'document_id', 'user',
        'page_count', 'created_at', 'due_date', 'is_overdue'
    ]
    list_filter = ['scan_type', 'created_at', 'is_archived']
    search_fields = ['title', 'document_id', 'description', 'user__username']
    readonly_fields = ['id', 'created_at', 'updated_at', 'due_date']
    inlines = [ScanPageInline]

    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'title', 'scan_type', 'description', 'user')
        }),
        ('Document Settings', {
            'fields': ('document_id', 'retention_days', 'due_date'),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('is_archived', 'created_at', 'updated_at')
        })
    )

    def page_count(self, obj):
        return obj.page_count
    page_count.short_description = "Pages"

    def is_overdue(self, obj):
        if obj.is_overdue:
            return format_html('<span style="color: red;">Yes</span>')
        elif obj.is_due_soon:
            return format_html('<span style="color: orange;">Soon</span>')
        return "No"
    is_overdue.short_description = "Overdue"


@admin.register(ScanPage)
class ScanPageAdmin(admin.ModelAdmin):
    list_display = ['scan', 'page_number', 'thumbnail_preview', 'created_at']
    list_filter = ['created_at', 'scan__scan_type']
    search_fields = ['scan__title', 'extracted_text']
    readonly_fields = ['id', 'thumbnail_preview', 'created_at']

    def thumbnail_preview(self, obj):
        if obj.thumbnail:
            return format_html(
                '<img src="{}" style="max-height: 100px; max-width: 100px;" />',
                obj.thumbnail.url
            )
        return "No thumbnail"
    thumbnail_preview.short_description = "Thumbnail"

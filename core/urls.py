from django.urls import path
from django.shortcuts import redirect
from . import views

app_name = 'core'

urlpatterns = [
    # Main pages
    path('', views.dashboard, name='dashboard'),
    path('settings/', views.settings_view, name='settings'),

    # Import/Export URLs
    path('settings/export/start/', views.start_export, name='start_export'),
    path('settings/export/status/<uuid:operation_id>/', views.export_status, name='export_status'),
    path('settings/export/download/<uuid:operation_id>/', views.download_export, name='download_export'),

    path('settings/import/upload/', views.upload_import_file, name='upload_import_file'),
    path('settings/import/validation/<uuid:operation_id>/', views.import_validation_status, name='import_validation_status'),
    path('settings/import/start/<uuid:operation_id>/', views.start_import, name='start_import'),
    path('settings/import/status/<uuid:operation_id>/', views.import_status, name='import_status'),

    path('settings/operation/logs/<uuid:operation_id>/', views.operation_logs, name='operation_logs'),
    path('settings/cleanup/', views.cleanup_old_operations, name='cleanup_old_operations'),
]

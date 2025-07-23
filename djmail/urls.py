from django.urls import path
from . import views

app_name = 'djmail'

urlpatterns = [
    # User Interface (Roundcube-like)
    path('', views.index, name='index'),
    path('email/<int:email_id>/', views.email_detail, name='email_detail'),
    path('compose/', views.compose, name='compose'),
    path('reply/<int:reply_to>/', views.compose, {'reply_to': True}, name='reply'),
    path('forward/<int:forward>/', views.compose, {'forward': True}, name='forward'),

    # Admin Interface (Superuser only)
    path('admin/', views.admin_dashboard, name='admin_dashboard'),
    path('admin/accounts/', views.admin_accounts, name='admin_accounts'),
    path('admin/accounts/add/', views.admin_add_account, name='admin_add_account'),
    path('admin/accounts/edit/<int:account_id>/', views.admin_edit_account, name='admin_edit_account'),
    path('admin/accounts/delete/<int:account_id>/', views.admin_delete_account, name='admin_delete_account'),
    path('admin/users/', views.admin_user_access, name='admin_user_access'),
    path('admin/users/<int:user_id>/accounts/', views.admin_user_account_access, name='admin_user_account_access'),
    path('admin/access/grant/', views.admin_grant_access, name='admin_grant_access'),
    path('admin/access/revoke/<int:access_id>/', views.admin_revoke_access, name='admin_revoke_access'),
    path('admin/logs/', views.admin_email_logs, name='admin_email_logs'),

    # Legacy URLs (for existing templates and redirects)
    path('accounts/', views.accounts, name='accounts'),
    path('accounts/add/', views.add_account, name='add_account'),
    path('accounts/edit/<int:account_id>/', views.edit_account, name='edit_account'),
    path('accounts/delete/<int:account_id>/', views.delete_account, name='delete_account'),
    path('settings/', views.mail_settings, name='mail_settings'),
    
    # Email actions
    path('fetch/', views.fetch_new_emails, name='fetch_emails'),
    path('fetch/<int:account_id>/', views.fetch_new_emails, name='fetch_account_emails'),
    path('mark-read/<int:email_id>/', views.mark_email_read, name='mark_email_read'),
    path('mark-unread/<int:email_id>/', views.mark_email_unread, name='mark_email_unread'),
    path('toggle-flag/<int:email_id>/', views.toggle_email_flag, name='toggle_email_flag'),
    path('move/<int:email_id>/to/<str:folder_type>/', views.move_to_folder, name='move_to_folder'),
    path('delete/<int:email_id>/', views.delete_email, name='delete_email'),
    path('retry/<int:email_id>/', views.retry_email, name='retry_email'),
    path('attachment/<int:attachment_id>/', views.download_attachment, name='download_attachment'),
    
    # Task management
    path('tasks/', views.tasks, name='tasks'),
    path('tasks/<int:task_id>/', views.task_detail, name='task_detail'),
    path('tasks/update-status/<int:task_id>/', views.task_status_update, name='task_status_update'),
    path('email/<int:email_id>/create-task/', views.create_task_for_email, name='create_task_for_email'),
]

from django.urls import path
from . import views

app_name = 'djmail'

urlpatterns = [
    # Main views
    path('', views.index, name='index'),
    path('email/<int:email_id>/', views.email_detail, name='email_detail'),
    path('compose/', views.compose, name='compose'),
    path('reply/<int:reply_to>/', views.compose, {'reply_to': True}, name='reply'),
    path('forward/<int:forward>/', views.compose, {'forward': True}, name='forward'),
    
    # Account management
    path('accounts/', views.accounts, name='accounts'),
    path('accounts/add/', views.add_account, name='add_account'),
    path('accounts/edit/<int:account_id>/', views.edit_account, name='edit_account'),
    path('accounts/delete/<int:account_id>/', views.delete_account, name='delete_account'),
    
    # Email actions
    path('fetch/', views.fetch_new_emails, name='fetch_emails'),
    path('fetch/<int:account_id>/', views.fetch_new_emails, name='fetch_account_emails'),
    path('mark-read/<int:email_id>/', views.mark_email_read, name='mark_email_read'),
    path('mark-unread/<int:email_id>/', views.mark_email_unread, name='mark_email_unread'),
    path('toggle-flag/<int:email_id>/', views.toggle_email_flag, name='toggle_email_flag'),
    path('move/<int:email_id>/to/<str:folder_type>/', views.move_to_folder, name='move_to_folder'),
    path('attachment/<int:attachment_id>/', views.download_attachment, name='download_attachment'),
    
    # Task management
    path('tasks/', views.tasks, name='tasks'),
    path('tasks/<int:task_id>/', views.task_detail, name='task_detail'),
    path('tasks/update-status/<int:task_id>/', views.task_status_update, name='task_status_update'),
    path('email/<int:email_id>/create-task/', views.create_task_for_email, name='create_task_for_email'),
]

from django.urls import path
from django.shortcuts import redirect
from . import views

app_name = 'djsql'

urlpatterns = [
    # Main pages
    path('', views.djsql, name='djsql'),
    
    # Server management
    path('api/servers/add/', views.add_server, name='add_server'),
    path('api/servers/<int:server_id>/edit/', views.edit_server, name='edit_server'),
    path('api/servers/<int:server_id>/delete/', views.delete_server, name='delete_server'),
    path('api/servers/<int:server_id>/databases/', views.list_databases, name='list_databases'),
    
    # Replication setup and management
    path('replication/setup/<int:step>/', views.setup_replication_step, name='setup_replication_step'),
    path('replication/setup/', lambda request: redirect('djsql:setup_replication_step', step=1), name='setup_replication'),
    path('api/replication/<int:link_id>/status/', views.replication_status, name='replication_status'),
    path('api/replication/<int:link_id>/delete/', views.delete_replication, name='delete_replication'),
    path('api/replication/<int:link_id>/unlink_database/', views.unlink_database, name='unlink_database'),
    path('api/servers/<int:server_id>/clean/', views.clean_replica, name='clean_replica'),
]

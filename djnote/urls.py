from django.urls import path
from . import views

app_name = 'djnote'

urlpatterns = [
    # Main views
    path('', views.index, name='index'),
    path('create/', views.create_scan, name='create'),
    path('due/', views.due_documents, name='due_documents'),
    path('archived/', views.archived_documents, name='archived'),
    
    # Scan management
    path('scan/<int:scan_id>/', views.scan_detail, name='detail'),
    path('scan/<int:scan_id>/edit/', views.edit_scan, name='edit'),
    path('scan/<int:scan_id>/delete/', views.delete_scan, name='delete'),
    path('scan/<int:scan_id>/archive/', views.archive_scan, name='archive'),
    path('scan/<int:scan_id>/restore/', views.restore_scan, name='restore'),
    path('scan/<int:scan_id>/add-pages/', views.add_pages, name='add_pages'),
    path('scan/<int:scan_id>/reorder-pages/', views.reorder_pages, name='reorder_pages'),

    # Page management
    path('page/<int:page_id>/delete/', views.delete_page, name='delete_page'),
]

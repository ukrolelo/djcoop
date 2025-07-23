from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),

    # Authentication URLs (allauth)
    path('accounts/', include('allauth.urls')),

    # Dashboard at root
    path('', include('core.urls')),
    # Add djsql URLs
    path('djsql/', include('djsql.urls', namespace='djsql')),
    # Add djmail URLs
    path('mail/', include('djmail.urls')),
    # Add djnote URLs
    path('notes/', include('djnote.urls', namespace='djnote')),
]

# Add static and media file serving for development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

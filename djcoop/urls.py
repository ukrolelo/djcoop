from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    # Root URL now redirects to dashboard
    path('', lambda request: redirect('core:dashboard')),
    # Add core URLs
    path('dashboard/', include('core.urls')),
    # Add djsql URLs
    path('djsql/', include('djsql.urls', namespace='djsql')),
    # Add djmail URLs
    path('mail/', include('djmail.urls')),
]

# Add static and media file serving for development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

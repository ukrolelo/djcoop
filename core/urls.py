from django.urls import path
from django.shortcuts import redirect
from . import views

app_name = 'core'

urlpatterns = [
    # Main pages
    path('', views.dashboard, name='dashboard'),
    path('settings/', views.settings, name='settings'),
]

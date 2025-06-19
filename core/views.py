from django.shortcuts import render

def dashboard(request):
    return render(request, 'core/dashboard.html', {
        'title': 'Dashboard',
        'active_menu': 'dashboard'
    })

def settings(request):
    return render(request, 'core/settings.html', {
        'title': 'Settings',
        'active_menu': 'settings'
    })

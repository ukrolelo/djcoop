from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.urls import reverse
from django.db.models import Q
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST
from django.utils import timezone
import json

from .models import EmailAccount, EmailFolder, Email, EmailAttachment, Task, EmailAccountAccess
from .forms import EmailAccountForm, ComposeEmailForm, TaskForm, TaskUpdateForm, EmailSearchForm
from .utils import fetch_emails, send_email
from djsql.utils import encrypt_data, decrypt_data
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required, user_passes_test

@login_required
def index(request):
    """Main mail client view - User interface (Roundcube-like)"""
    current_user = request.user

    # Get accounts accessible to the current user
    if current_user:
        if current_user.is_superuser:
            accessible_accounts = EmailAccount.objects.all()
        else:
            accessible_accounts = current_user.get_accessible_email_accounts()
    else:
        accessible_accounts = EmailAccount.objects.none()

    # Get selected account (from URL parameter or default)
    account_id = request.GET.get('account')
    if account_id:
        try:
            account = accessible_accounts.get(id=account_id)
        except EmailAccount.DoesNotExist:
            account = accessible_accounts.first()
    else:
        # Default to first accessible account
        account = accessible_accounts.first()

    # Initialize empty data for when no account is accessible
    folders = []
    folder = None
    emails = []
    current_folder = 'inbox'
    search_form = EmailSearchForm()

    if not account:
        # Show the interface even without accessible accounts
        context = {
            'title': 'Mail',
            'active_menu': 'djmail',
            'account': None,
            'accessible_accounts': accessible_accounts,
            'folders': folders,
            'folder': folder,
            'current_folder': current_folder,
            'emails': emails,
            'search_form': search_form,
        }
        return render(request, 'djmail/index.html', context)
    
    # Get folders for the account with email counts
    folders = EmailFolder.objects.filter(account=account).order_by('folder_type')

    # Default to inbox folder
    current_folder = request.GET.get('folder', 'inbox')
    folder = get_object_or_404(EmailFolder, account=account, folder_type=current_folder)

    # Get emails for the selected folder
    emails = Email.objects.filter(account=account, folder=folder).select_related('folder').prefetch_related('attachments').order_by('-date_received')
    
    # Search form
    search_form = EmailSearchForm(request.GET or None)
    if search_form.is_valid() and search_form.cleaned_data.get('query'):
        query = search_form.cleaned_data['query']
        emails = emails.filter(
            Q(subject__icontains=query) | 
            Q(sender__icontains=query) |
            Q(sender_name__icontains=query) |
            Q(recipients__icontains=query) |
            Q(body_text__icontains=query)
        )
    
    # Apply date filters if specified
    if search_form.is_valid():
        from_date = search_form.cleaned_data.get('from_date')
        to_date = search_form.cleaned_data.get('to_date')
        has_attachment = search_form.cleaned_data.get('has_attachment')
        
        if from_date:
            emails = emails.filter(date_received__date__gte=from_date)
        
        if to_date:
            emails = emails.filter(date_received__date__lte=to_date)
        
        if has_attachment:
            emails = emails.filter(attachments__isnull=False).distinct()
    
    # Paginate results - show more emails for the new interface
    paginator = Paginator(emails, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'title': 'Mail',
        'active_menu': 'djmail',
        'account': account,
        'accessible_accounts': accessible_accounts,
        'folders': folders,
        'folder': folder,
        'current_folder': current_folder,
        'emails': page_obj,
        'search_form': search_form,
    }
    
    return render(request, 'djmail/index.html', context)

def email_detail(request, email_id):
    """View a single email"""
    email_obj = get_object_or_404(Email, pk=email_id)
    
    # Mark as read if not already
    if not email_obj.read:
        email_obj.read = True
        email_obj.save()
    
    # Get related tasks
    related_tasks = Task.objects.filter(related_email=email_obj)
    
    # New task form
    task_form = TaskForm(initial={'related_email': email_obj})
    
    context = {
        'title': email_obj.subject,
        'active_menu': 'djmail',
        'email': email_obj,
        'related_tasks': related_tasks,
        'task_form': task_form
    }
    
    return render(request, 'djmail/email_detail.html', context)

def compose(request, reply_to=None, forward=None):
    """Compose a new email, optionally as a reply or forward"""
    # Get default account
    try:
        account = EmailAccount.objects.filter(is_default=True).first() or EmailAccount.objects.first()
    except EmailAccount.DoesNotExist:
        messages.error(request, "No email accounts configured. Please add an account first.")
        return redirect('djmail:accounts')
    
    initial_data = {}
    reply_email = None
    forward_email = None
    
    # Handle reply
    if reply_to:
        reply_email = get_object_or_404(Email, pk=reply_to)
        initial_data['to'] = reply_email.sender
        initial_data['subject'] = f"Re: {reply_email.subject}"
        initial_data['body'] = f"\n\n\n-------- Original Message --------\nFrom: {reply_email.sender}\nDate: {reply_email.date_received}\nSubject: {reply_email.subject}\n\n{reply_email.body_text}"
    
    # Handle forward
    if forward:
        forward_email = get_object_or_404(Email, pk=forward)
        initial_data['subject'] = f"Fwd: {forward_email.subject}"
        initial_data['body'] = f"\n\n\n-------- Forwarded Message --------\nFrom: {forward_email.sender}\nDate: {forward_email.date_received}\nSubject: {forward_email.subject}\n\n{forward_email.body_text}"
    
    # Handle form submission
    if request.method == 'POST':
        form = ComposeEmailForm(request.POST, request.FILES)
        if form.is_valid():
            # Parse recipient lists
            to_emails = [email.strip() for email in form.cleaned_data['to'].split(',')]
            cc_emails = [email.strip() for email in form.cleaned_data['cc'].split(',')] if form.cleaned_data['cc'] else None
            bcc_emails = [email.strip() for email in form.cleaned_data['bcc'].split(',')] if form.cleaned_data['bcc'] else None
            
            # Get attachment (since we can't handle multiple files with standard Django forms)
            attachments = []
            if 'attachments' in request.FILES:
                attachments = [request.FILES['attachments']]
            
            # Send email
            # Log email sending operation
            from .mail_logger import get_mail_logger
            send_logger = get_mail_logger("SEND_EMAIL")
            send_logger.send_start(
                subject=form.cleaned_data['subject'],
                to_emails=to_emails,
                from_email=account.email
            )

            success, error = send_email(
                account=account,
                to_emails=to_emails,
                subject=form.cleaned_data['subject'],
                body_text=form.cleaned_data['body'],
                cc_emails=cc_emails,
                bcc_emails=bcc_emails,
                attachments=attachments,
                user=request.user  # Pass user for logging
            )

            # Log send completion
            send_logger.send_complete(success=success, error=error)
            
            if success:
                messages.success(request, "Email sent successfully")
                
                # Mark original as replied if this was a reply
                if reply_email:
                    reply_email.replied = True
                    reply_email.save()
                
                # Mark original as forwarded if this was a forward
                if forward_email:
                    forward_email.forwarded = True
                    forward_email.save()
                
                return redirect('djmail:index')
            else:
                messages.error(request, f"Failed to send email: {error}")
    else:
        form = ComposeEmailForm(initial=initial_data)
    
    context = {
        'title': 'Compose Email',
        'active_menu': 'djmail',
        'form': form,
        'account': account,
        'reply_to': reply_email,
        'forward': forward_email
    }
    
    return render(request, 'djmail/compose.html', context)

def accounts(request):
    """View and manage email accounts"""
    accounts = EmailAccount.objects.all().order_by('-is_default', 'name')
    
    context = {
        'title': 'Email Accounts',
        'active_menu': 'djmail',
        'accounts': accounts
    }
    
    return render(request, 'djmail/accounts.html', context)

def add_account(request):
    """Add a new email account"""
    if request.method == 'POST':
        form = EmailAccountForm(request.POST)
        if form.is_valid():
            # Don't save yet, we need to encrypt the password first
            account = form.save(commit=False)

            # Encrypt the password before saving
            plain_password = form.cleaned_data['password']
            account.password = encrypt_data(plain_password)
            account.save()

            # If this is the first account or marked as default, set as default
            if account.is_default or EmailAccount.objects.count() == 1:
                # Unset other defaults
                EmailAccount.objects.exclude(pk=account.pk).update(is_default=False)
                account.is_default = True
                account.save()
                
                # Create default system folders
                for folder_type, folder_name in [
                    ('inbox', 'Inbox'),
                    ('sent', 'Sent'),
                    ('drafts', 'Drafts'),
                    ('trash', 'Trash')
                ]:
                    EmailFolder.objects.create(
                        account=account,
                        name=folder_name,
                        folder_type=folder_type,
                        is_system=True
                    )
            
            messages.success(request, f"Account '{account.name}' added successfully")
            return redirect('djmail:accounts')
    else:
        form = EmailAccountForm()
    
    context = {
        'title': 'Add Email Account',
        'active_menu': 'djmail',
        'form': form
    }
    
    return render(request, 'djmail/add_account.html', context)

def edit_account(request, account_id):
    """Edit an existing email account"""
    account = get_object_or_404(EmailAccount, pk=account_id)

    if request.method == 'POST':
        form = EmailAccountForm(request.POST, instance=account)
        if form.is_valid():
            # Don't save yet, we need to handle password encryption
            updated_account = form.save(commit=False)

            # Check if password was changed
            new_password = form.cleaned_data['password']
            if new_password:  # If password field is not empty
                # Encrypt the new password
                updated_account.password = encrypt_data(new_password)
            # If password field is empty, keep the existing encrypted password

            updated_account.save()

            # If marked as default, unset other defaults
            if updated_account.is_default:
                EmailAccount.objects.exclude(pk=updated_account.pk).update(is_default=False)
            
            messages.success(request, f"Account '{updated_account.name}' updated successfully")
            return redirect('djmail:accounts')
    else:
        form = EmailAccountForm(instance=account)
    
    context = {
        'title': 'Edit Email Account',
        'active_menu': 'djmail',
        'form': form,
        'account': account
    }
    
    return render(request, 'djmail/edit_account.html', context)

def delete_account(request, account_id):
    """Delete an email account"""
    account = get_object_or_404(EmailAccount, pk=account_id)
    
    if request.method == 'POST':
        account_name = account.name
        account.delete()
        
        # If there are more accounts and this was the default, set a new default
        remaining_accounts = EmailAccount.objects.all()
        if remaining_accounts.exists() and account.is_default:
            new_default = remaining_accounts.first()
            new_default.is_default = True
            new_default.save()
        
        messages.success(request, f"Account '{account_name}' deleted successfully")
        return redirect('djmail:accounts')
    
    context = {
        'title': 'Delete Email Account',
        'active_menu': 'djmail',
        'account': account
    }
    
    return render(request, 'djmail/delete_account.html', context)

def fetch_new_emails(request, account_id=None):
    """Fetch new emails from the server"""
    from .mail_logger import get_mail_logger

    # Initialize logger for this fetch operation
    logger = get_mail_logger("FETCH_EMAILS")

    if account_id:
        accounts = [get_object_or_404(EmailAccount, pk=account_id)]
        logger.info(f"Fetching emails for specific account", account_id=account_id)
    else:
        accounts = EmailAccount.objects.all()
        logger.info(f"Fetching emails for all accounts", account_count=accounts.count())

    total_new = 0
    errors = []

    for account in accounts:
        try:
            logger.fetch_start(account.email, account.pop3_server)
            new_emails = fetch_emails(account)
            total_new += len(new_emails)
            logger.info(f"Successfully fetched emails",
                       account=account.email,
                       new_emails=len(new_emails))
        except Exception as e:
            error_msg = f"Error fetching emails for {account.name}: {str(e)}"
            errors.append(error_msg)
            logger.error(f"Failed to fetch emails",
                        account=account.email,
                        error=e)

    # Log final results
    logger.fetch_complete()
    logger.info(f"Fetch operation completed",
               total_new_emails=total_new,
               error_count=len(errors))

    if errors:
        messages.error(request, "\n".join(errors))

    if total_new > 0:
        messages.success(request, f"Successfully fetched {total_new} new email(s)")
    else:
        messages.info(request, "No new emails found")

    return redirect(request.META.get('HTTP_REFERER', reverse('djmail:index')))

def tasks(request):
    """View and manage tasks"""
    # Filter tasks based on query parameters
    status_filter = request.GET.get('status', '')
    priority_filter = request.GET.get('priority', '')
    
    tasks = Task.objects.all().order_by('-created_at')
    
    if status_filter:
        tasks = tasks.filter(status=status_filter)
    
    if priority_filter:
        tasks = tasks.filter(priority=priority_filter)
    
    # Paginate results
    paginator = Paginator(tasks, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # Create task form
    if request.method == 'POST':
        form = TaskForm(request.POST)
        if form.is_valid():
            task = form.save()
            messages.success(request, f"Task '{task.title}' created successfully")
            return redirect('djmail:tasks')
    else:
        form = TaskForm()
    
    context = {
        'title': 'Task Manager',
        'active_menu': 'djmail',
        'tasks': page_obj,
        'form': form,
        'status_filter': status_filter,
        'priority_filter': priority_filter
    }
    
    return render(request, 'djmail/tasks.html', context)

def task_detail(request, task_id):
    """View a single task"""
    task = get_object_or_404(Task, pk=task_id)
    
    if request.method == 'POST':
        form = TaskForm(request.POST, instance=task)
        if form.is_valid():
            updated_task = form.save()
            
            if updated_task.status == 'completed' and not updated_task.completed_at:
                updated_task.completed_at = timezone.now()
                updated_task.save()
            
            messages.success(request, f"Task '{updated_task.title}' updated successfully")
            return redirect('djmail:task_detail', task_id=task.id)
    else:
        form = TaskForm(instance=task)
    
    context = {
        'title': task.title,
        'active_menu': 'djmail',
        'task': task,
        'form': form
    }
    
    return render(request, 'djmail/task_detail.html', context)

@require_POST
def task_status_update(request, task_id):
    """Update task status via AJAX"""
    task = get_object_or_404(Task, pk=task_id)
    
    form = TaskUpdateForm(request.POST, instance=task)
    if form.is_valid():
        updated_task = form.save()
        
        # Update completed_at if status changed to completed
        if updated_task.status == 'completed' and not updated_task.completed_at:
            updated_task.completed_at = timezone.now()
            updated_task.save()
        
        return JsonResponse({
            'success': True,
            'task_id': task.id,
            'new_status': updated_task.status,
            'status_display': updated_task.get_status_display()
        })
    
    return JsonResponse({
        'success': False,
        'errors': form.errors
    }, status=400)

def create_task_for_email(request, email_id):
    """Create a task linked to an email"""
    email_obj = get_object_or_404(Email, pk=email_id)
    
    if request.method == 'POST':
        form = TaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.related_email = email_obj
            task.save()
            
            messages.success(request, f"Task '{task.title}' created successfully")
            return redirect('djmail:email_detail', email_id=email_id)
    else:
        # Default title based on email subject
        form = TaskForm(initial={
            'title': f"Follow up: {email_obj.subject}",
            'related_email': email_obj
        })
    
    context = {
        'title': 'Create Task',
        'active_menu': 'djmail',
        'form': form,
        'email': email_obj
    }
    
    return render(request, 'djmail/create_task.html', context)

def download_attachment(request, attachment_id):
    """Download an email attachment"""
    attachment = get_object_or_404(EmailAttachment, pk=attachment_id)
    
    response = HttpResponse(
        attachment.file.read(),
        content_type=attachment.content_type or 'application/octet-stream'
    )
    response['Content-Disposition'] = f'attachment; filename="{attachment.filename}"'
    
    return response

def mark_email_read(request, email_id):
    """Mark email as read"""
    email_obj = get_object_or_404(Email, pk=email_id)
    email_obj.read = True
    email_obj.save()
    
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'success': True})
    
    return redirect(request.META.get('HTTP_REFERER', reverse('djmail:index')))

def mark_email_unread(request, email_id):
    """Mark email as unread"""
    email_obj = get_object_or_404(Email, pk=email_id)
    email_obj.read = False
    email_obj.save()
    
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'success': True})
    
    return redirect(request.META.get('HTTP_REFERER', reverse('djmail:index')))

def toggle_email_flag(request, email_id):
    """Toggle email flagged status"""
    email_obj = get_object_or_404(Email, pk=email_id)
    email_obj.flagged = not email_obj.flagged
    email_obj.save()
    
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'flagged': email_obj.flagged
        })
    
    return redirect(request.META.get('HTTP_REFERER', reverse('djmail:index')))

def move_to_folder(request, email_id, folder_type):
    """Move email to a different folder"""
    email_obj = get_object_or_404(Email, pk=email_id)
    
    # Get the destination folder or create it
    folder, created = EmailFolder.objects.get_or_create(
        account=email_obj.account,
        folder_type=folder_type,
        defaults={
            'name': folder_type.capitalize(),
            'is_system': True
        }
    )
    
    # Update email's folder
    email_obj.folder = folder
    email_obj.save()

    messages.success(request, f"Email moved to {folder.name}")

    return redirect(request.META.get('HTTP_REFERER', reverse('djmail:index')))

def mail_settings(request):
    """Mail settings and account management view"""
    # Get all email accounts
    accounts = EmailAccount.objects.all().order_by('name')

    # Get default account or first available
    try:
        account = EmailAccount.objects.filter(is_default=True).first() or EmailAccount.objects.first()
    except EmailAccount.DoesNotExist:
        account = None

    # Get folders for the account if available
    folders = []
    recent_tasks = []
    if account:
        folders = EmailFolder.objects.filter(account=account).order_by('folder_type')
        recent_tasks = Task.objects.filter(status__in=['not_started', 'in_progress']).order_by('-created_at')[:5]

    context = {
        'title': 'Mail Settings',
        'active_menu': 'djmail',
        'accounts': accounts,
        'account': account,
        'folders': folders,
        'recent_tasks': recent_tasks
    }

    return render(request, 'djmail/settings.html', context)

# =============================================================================
# ADMIN VIEWS (Superuser only)
# =============================================================================

@login_required
@user_passes_test(lambda u: u.is_superuser or u.is_staff)
def admin_dashboard(request):
    """Admin dashboard for mail management"""

    accounts = EmailAccount.objects.all()
    total_users = User.objects.count()
    total_accesses = EmailAccountAccess.objects.count()

    context = {
        'title': 'Mail Administration',
        'active_menu': 'djmail',
        'accounts': accounts,
        'total_users': total_users,
        'total_accesses': total_accesses,
    }
    return render(request, 'djmail/admin/dashboard.html', context)

@login_required
@user_passes_test(lambda u: u.is_superuser or u.is_staff)
def admin_accounts(request):
    """Admin view for managing email accounts"""
    return redirect('djmail:accounts')  # Redirect to existing accounts view for now

@login_required
@user_passes_test(lambda u: u.is_superuser or u.is_staff)
def admin_add_account(request):
    """Admin view for adding email accounts"""
    return redirect('djmail:add_account')  # Redirect to existing add account view for now

@login_required
@user_passes_test(lambda u: u.is_superuser or u.is_staff)
def admin_edit_account(request, account_id):
    """Admin view for editing email accounts"""
    return redirect('djmail:edit_account', account_id=account_id)

@login_required
@user_passes_test(lambda u: u.is_superuser or u.is_staff)
def admin_delete_account(request, account_id):
    """Admin view for deleting email accounts"""
    return redirect('djmail:delete_account', account_id=account_id)

@login_required
@user_passes_test(lambda u: u.is_superuser or u.is_staff)
def admin_user_access(request):
    """Admin view for managing user access to email accounts"""

    users = User.objects.all().prefetch_related('email_account_accesses__email_account')
    accounts = EmailAccount.objects.all().prefetch_related('user_accesses__user')
    total_grants = EmailAccountAccess.objects.count()

    context = {
        'title': 'User Access Management',
        'active_menu': 'djmail',
        'users': users,
        'accounts': accounts,
        'total_grants': total_grants,
    }
    return render(request, 'djmail/admin/user_access.html', context)

@login_required
@user_passes_test(lambda u: u.is_superuser or u.is_staff)
def admin_user_account_access(request, user_id):
    """Admin view for managing a specific user's account access"""

    user = get_object_or_404(User, pk=user_id)
    user_accesses = EmailAccountAccess.objects.filter(user=user).select_related('email_account')
    available_accounts = EmailAccount.objects.exclude(user_accesses__user=user)

    context = {
        'title': f'Access for {user.username}',
        'active_menu': 'djmail',
        'target_user': user,
        'user_accesses': user_accesses,
        'available_accounts': available_accounts,
    }
    return render(request, 'djmail/admin/user_account_access.html', context)

@login_required
@user_passes_test(lambda u: u.is_superuser or u.is_staff)
def admin_grant_access(request):
    """Admin view for granting user access to email accounts"""

    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        account_id = request.POST.get('account_id')
        access_level = request.POST.get('access_level', 'read')

        try:
            user = User.objects.get(pk=user_id)
            account = EmailAccount.objects.get(pk=account_id)

            # Create or update access
            access, created = EmailAccountAccess.objects.get_or_create(
                user=user,
                email_account=account,
                defaults={
                    'access_level': access_level,
                    'granted_by': request.user if hasattr(request, 'user') else None,
                }
            )

            if created:
                messages.success(request, f'Access granted to {user.username} for {account.name}')
            else:
                access.access_level = access_level
                access.save()
                messages.info(request, f'Access updated for {user.username} on {account.name}')

        except (User.DoesNotExist, EmailAccount.DoesNotExist):
            messages.error(request, 'Invalid user or account')

    return redirect('djmail:admin_user_access')

@login_required
@user_passes_test(lambda u: u.is_superuser or u.is_staff)
def admin_revoke_access(request, access_id):
    """Admin view for revoking user access to email accounts"""

    access = get_object_or_404(EmailAccountAccess, pk=access_id)
    user = access.user
    account = access.email_account

    access.delete()
    messages.success(request, f'Access revoked for {user.username} on {account.name}')

    return redirect('djmail:admin_user_access')


@login_required
@user_passes_test(lambda u: u.is_superuser or u.is_staff)
def admin_email_logs(request):
    """Admin view for viewing email server communication logs"""
    from .models import EmailServerLog

    # Get filter parameters
    log_type = request.GET.get('log_type', '')
    status = request.GET.get('status', '')
    account_id = request.GET.get('account_id', '')

    # Base queryset
    logs = EmailServerLog.objects.all().select_related('email_account', 'user', 'email')

    # Apply filters
    if log_type:
        logs = logs.filter(log_type=log_type)
    if status:
        logs = logs.filter(status=status)
    if account_id:
        logs = logs.filter(email_account_id=account_id)

    # Pagination
    paginator = Paginator(logs, 50)  # Show 50 logs per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Get filter options
    log_types = EmailServerLog.LOG_TYPES
    statuses = EmailServerLog.STATUS_CHOICES
    accounts = EmailAccount.objects.all()

    # Statistics
    total_logs = EmailServerLog.objects.count()
    error_logs = EmailServerLog.objects.filter(status='error').count()
    today_logs = EmailServerLog.objects.filter(timestamp__date=timezone.now().date()).count()

    context = {
        'title': 'Email Server Logs',
        'active_menu': 'djmail',
        'logs': page_obj,
        'log_types': log_types,
        'statuses': statuses,
        'accounts': accounts,
        'current_filters': {
            'log_type': log_type,
            'status': status,
            'account_id': account_id,
        },
        'stats': {
            'total_logs': total_logs,
            'error_logs': error_logs,
            'today_logs': today_logs,
        }
    }
    return render(request, 'djmail/admin/email_logs.html', context)


@login_required
def delete_email(request, email_id):
    """Delete an email permanently"""
    email_obj = get_object_or_404(Email, pk=email_id)

    if request.method == 'POST':
        # Get the folder name for redirect
        folder_name = email_obj.folder.name.lower()

        # Delete the email
        email_obj.delete()

        messages.success(request, f'Email "{email_obj.subject}" has been permanently deleted.')

        # Redirect back to the appropriate folder
        if folder_name == 'inbox':
            return redirect('djmail:index')
        else:
            # Use reverse with query parameters for proper URL construction
            from django.urls import reverse
            from django.http import HttpResponseRedirect
            url = reverse('djmail:index') + f'?folder={folder_name}'
            return HttpResponseRedirect(url)

    # If GET request, show confirmation (this shouldn't happen with modal, but just in case)
    return redirect('djmail:email_detail', email_id=email_id)


@login_required
def retry_email(request, email_id):
    """Retry sending an email from Outbox"""
    email_obj = get_object_or_404(Email, pk=email_id)

    # Only allow retry for emails in Outbox
    if email_obj.folder.folder_type != 'outbox':
        messages.error(request, 'Only emails in Outbox can be retried.')
        return redirect('djmail:email_detail', email_id=email_id)

    if request.method == 'POST':
        from .mail_logger import get_mail_logger
        from .utils import send_email

        # Log retry attempt
        retry_logger = get_mail_logger("RETRY_EMAIL")
        retry_logger.info(f"Retrying email send",
                         email_id=email_id,
                         subject=email_obj.subject)

        # Parse recipients
        to_emails = [email.strip() for email in email_obj.recipients.split(',') if email.strip()]
        cc_emails = [email.strip() for email in email_obj.cc.split(',') if email.strip() and email_obj.cc]
        bcc_emails = [email.strip() for email in email_obj.bcc.split(',') if email.strip() and email_obj.bcc]

        # Attempt to resend
        success, error = send_email(
            account=email_obj.account,
            to_emails=to_emails,
            subject=email_obj.subject,
            body_text=email_obj.body_text,
            body_html=email_obj.body_html,
            cc_emails=cc_emails if cc_emails else None,
            bcc_emails=bcc_emails if bcc_emails else None,
            user=request.user
        )

        if success:
            # Delete the original email from Outbox since a new one was created and moved to Sent
            email_obj.delete()
            messages.success(request, f'Email "{email_obj.subject}" has been successfully resent.')
            return redirect('djmail:index') + '?folder=sent'
        else:
            messages.error(request, f'Failed to resend email: {error}')
            return redirect('djmail:email_detail', email_id=email_id)

    # If GET request, redirect to email detail
    return redirect('djmail:email_detail', email_id=email_id)

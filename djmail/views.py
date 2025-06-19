from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.urls import reverse
from django.db.models import Q
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST
from django.utils import timezone
import json

from .models import EmailAccount, EmailFolder, Email, EmailAttachment, Task
from .forms import EmailAccountForm, ComposeEmailForm, TaskForm, TaskUpdateForm, EmailSearchForm
from .utils import fetch_emails, send_email

def index(request):
    """Main email dashboard view"""
    # Get default account or first available
    try:
        account = EmailAccount.objects.filter(is_default=True).first() or EmailAccount.objects.first()
    except EmailAccount.DoesNotExist:
        account = None
    
    if not account:
        messages.warning(request, "No email accounts configured. Please add an account first.")
        return redirect('djmail:accounts')
    
    # Get folders for the account
    folders = EmailFolder.objects.filter(account=account).order_by('folder_type')
    
    # Default to inbox folder
    current_folder = request.GET.get('folder', 'inbox')
    folder = get_object_or_404(EmailFolder, account=account, folder_type=current_folder)
    
    # Get emails for the selected folder
    emails = Email.objects.filter(account=account, folder=folder).order_by('-date_received')
    
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
    
    # Paginate results
    paginator = Paginator(emails, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # Tasks
    recent_tasks = Task.objects.filter(status__in=['not_started', 'in_progress']).order_by('-created_at')[:5]
    
    context = {
        'title': 'Mail Client',
        'active_menu': 'djmail',
        'account': account,
        'folders': folders,
        'current_folder': current_folder,
        'emails': page_obj,
        'search_form': search_form,
        'recent_tasks': recent_tasks
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
            success, error = send_email(
                account=account,
                to_emails=to_emails,
                subject=form.cleaned_data['subject'],
                body_text=form.cleaned_data['body'],
                cc_emails=cc_emails,
                bcc_emails=bcc_emails,
                attachments=attachments
            )
            
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
            account = form.save()
            
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
            updated_account = form.save()
            
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
    if account_id:
        accounts = [get_object_or_404(EmailAccount, pk=account_id)]
    else:
        accounts = EmailAccount.objects.all()
    
    total_new = 0
    errors = []
    
    for account in accounts:
        try:
            new_emails = fetch_emails(account)
            total_new += len(new_emails)
        except Exception as e:
            errors.append(f"Error fetching emails for {account.name}: {str(e)}")
    
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

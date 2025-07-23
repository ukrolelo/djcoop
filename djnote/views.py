from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from PIL import Image
import io
import json

from .models import Scan, ScanPage
from .forms import ScanForm, BulkUploadForm, ScanPageFormSet


@login_required
def index(request):
    """Main djnote dashboard"""
    # Get user's scans
    scans = Scan.objects.filter(user=request.user, is_archived=False)

    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        scans = scans.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(document_id__icontains=search_query)
        )

    # Filter by type
    scan_type = request.GET.get('type', '')
    if scan_type in ['document', 'note']:
        scans = scans.filter(scan_type=scan_type)

    # Pagination
    paginator = Paginator(scans, 12)  # 12 scans per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Get due documents for sidebar alert
    due_documents = Scan.objects.filter(
        user=request.user,
        scan_type='document',
        due_date__lte=timezone.now() + timezone.timedelta(days=7),
        is_archived=False
    ).order_by('due_date')[:5]

    context = {
        'title': 'Notes & Documents',
        'active_menu': 'djnote',
        'page_obj': page_obj,
        'search_query': search_query,
        'scan_type': scan_type,
        'due_documents': due_documents,
        'total_scans': scans.count(),
    }
    return render(request, 'djnote/index.html', context)


@login_required
def create_scan(request):
    """Create a new scan"""
    if request.method == 'POST':
        form = ScanForm(request.POST)

        if form.is_valid():
            # Create the scan
            scan = form.save(commit=False)
            scan.user = request.user

            # Handle due_date from form
            due_date = form.cleaned_data.get('due_date')
            if due_date and scan.scan_type == 'document':
                # Convert date to datetime for due_date field
                from django.utils import timezone
                scan.due_date = timezone.make_aware(
                    timezone.datetime.combine(due_date, timezone.datetime.min.time())
                )

            scan.save()

            # Process uploaded images
            images = request.FILES.getlist('images')
            for i, image_file in enumerate(images, 1):
                # Create thumbnail
                thumbnail = create_thumbnail(image_file)

                # Create scan page
                scan_page = ScanPage(
                    scan=scan,
                    page_number=i,
                    image=image_file
                )
                scan_page.save()

                # Save thumbnail
                if thumbnail:
                    thumbnail_name = f"thumb_{scan_page.id}.jpg"
                    scan_page.thumbnail.save(
                        thumbnail_name,
                        thumbnail,
                        save=True
                    )

            messages.success(request, f'Scan "{scan.title}" created successfully with {len(images)} pages.')
            return redirect('djnote:detail', scan_id=scan.id)
    else:
        form = ScanForm()

    context = {
        'title': 'Create New Scan',
        'active_menu': 'djnote',
        'form': form,
    }
    return render(request, 'djnote/create.html', context)


@login_required
def scan_detail(request, scan_id):
    """View scan details and pages"""
    scan = get_object_or_404(Scan, id=scan_id, user=request.user)
    pages = scan.pages.all()

    context = {
        'title': f'Scan: {scan.title}',
        'active_menu': 'djnote',
        'scan': scan,
        'pages': pages,
    }
    return render(request, 'djnote/detail.html', context)


@login_required
def edit_scan(request, scan_id):
    """Edit scan details"""
    scan = get_object_or_404(Scan, id=scan_id, user=request.user)

    if request.method == 'POST':
        form = ScanForm(request.POST, instance=scan)
        if form.is_valid():
            # Handle due_date from form
            updated_scan = form.save(commit=False)
            due_date = form.cleaned_data.get('due_date')
            if due_date and updated_scan.scan_type == 'document':
                # Convert date to datetime for due_date field
                from django.utils import timezone
                updated_scan.due_date = timezone.make_aware(
                    timezone.datetime.combine(due_date, timezone.datetime.min.time())
                )
            elif updated_scan.scan_type == 'note':
                # Clear due_date for notes
                updated_scan.due_date = None

            updated_scan.save()
            messages.success(request, f'Scan "{scan.title}" updated successfully.')
            return redirect('djnote:detail', scan_id=scan.id)
    else:
        form = ScanForm(instance=scan)

    context = {
        'title': f'Edit: {scan.title}',
        'active_menu': 'djnote',
        'form': form,
        'scan': scan,
    }
    return render(request, 'djnote/edit.html', context)


@login_required
@require_http_methods(["POST"])
def delete_scan(request, scan_id):
    """Delete a scan"""
    scan = get_object_or_404(Scan, id=scan_id, user=request.user)
    title = scan.title
    scan.delete()
    messages.success(request, f'Scan "{title}" deleted successfully.')
    return redirect('djnote:index')


@login_required
def due_documents(request):
    """List documents that are due for deletion"""
    documents = Scan.objects.filter(
        user=request.user,
        scan_type='document',
        due_date__isnull=False,
        is_archived=False
    ).order_by('due_date')

    context = {
        'title': 'Due Documents',
        'active_menu': 'djnote',
        'documents': documents,
    }
    return render(request, 'djnote/due_documents.html', context)


@login_required
def add_pages(request, scan_id):
    """Add more pages to an existing scan"""
    scan = get_object_or_404(Scan, id=scan_id, user=request.user)

    if request.method == 'POST':
        images = request.FILES.getlist('images')
        if images:
            current_max_page = scan.pages.aggregate(
                max_page=models.Max('page_number')
            )['max_page'] or 0

            for i, image_file in enumerate(images, current_max_page + 1):
                # Create thumbnail
                thumbnail = create_thumbnail(image_file)

                # Create scan page
                scan_page = ScanPage(
                    scan=scan,
                    page_number=i,
                    image=image_file
                )
                scan_page.save()

                # Save thumbnail
                if thumbnail:
                    thumbnail_name = f"thumb_{scan_page.id}.jpg"
                    scan_page.thumbnail.save(
                        thumbnail_name,
                        thumbnail,
                        save=True
                    )

            messages.success(request, f'Added {len(images)} pages to "{scan.title}".')
            return redirect('djnote:detail', scan_id=scan.id)
        else:
            messages.error(request, 'Please select at least one image.')

    context = {
        'title': f'Add Pages: {scan.title}',
        'active_menu': 'djnote',
        'scan': scan,
    }
    return render(request, 'djnote/add_pages.html', context)


@login_required
@require_http_methods(["POST"])
def delete_page(request, page_id):
    """Delete a scan page"""
    page = get_object_or_404(ScanPage, id=page_id, scan__user=request.user)
    scan = page.scan
    page.delete()

    # Reorder remaining pages
    remaining_pages = scan.pages.order_by('page_number')
    for i, page in enumerate(remaining_pages, 1):
        if page.page_number != i:
            page.page_number = i
            page.save()

    messages.success(request, 'Page deleted successfully.')
    return redirect('djnote:detail', scan_id=scan.id)


@login_required
@require_http_methods(["POST"])
def archive_scan(request, scan_id):
    """Archive/unarchive a scan"""
    scan = get_object_or_404(Scan, id=scan_id, user=request.user)
    scan.is_archived = not scan.is_archived
    scan.save()

    action = "archived" if scan.is_archived else "unarchived"
    messages.success(request, f'Scan "{scan.title}" {action} successfully.')
    return redirect('djnote:index')


@login_required
def archived_documents(request):
    """View archived documents"""
    # Get user's archived scans
    archived_scans = Scan.objects.filter(user=request.user, is_archived=True)

    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        archived_scans = archived_scans.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(document_id__icontains=search_query)
        )

    # Filter by type
    scan_type = request.GET.get('type', '')
    if scan_type in ['document', 'note']:
        archived_scans = archived_scans.filter(scan_type=scan_type)

    # Pagination
    paginator = Paginator(archived_scans, 12)  # 12 scans per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'title': 'Archived Documents',
        'active_menu': 'djnote',
        'page_obj': page_obj,
        'search_query': search_query,
        'scan_type': scan_type,
        'total_archived': archived_scans.count(),
    }
    return render(request, 'djnote/archived.html', context)


@login_required
@require_http_methods(["POST"])
def restore_scan(request, scan_id):
    """Restore a scan from archive"""
    scan = get_object_or_404(Scan, id=scan_id, user=request.user, is_archived=True)
    scan.is_archived = False
    scan.save()

    messages.success(request, f'Scan "{scan.title}" restored from archive successfully.')
    return redirect('djnote:archived')


def create_thumbnail(image_file):
    """Create a thumbnail from an uploaded image"""
    try:
        # Open the image
        image = Image.open(image_file)

        # Convert to RGB if necessary
        if image.mode in ('RGBA', 'LA', 'P'):
            image = image.convert('RGB')

        # Create thumbnail
        image.thumbnail((300, 300), Image.Resampling.LANCZOS)

        # Save to BytesIO
        thumb_io = io.BytesIO()
        image.save(thumb_io, format='JPEG', quality=85)
        thumb_io.seek(0)

        from django.core.files.base import ContentFile
        return ContentFile(thumb_io.read())

    except Exception as e:
        print(f"Error creating thumbnail: {e}")
        return None


# Import models for the aggregate function
from django.db import models


@login_required
@require_http_methods(["POST"])
def reorder_pages(request, scan_id):
    """Reorder pages in a scan via AJAX"""
    scan = get_object_or_404(Scan, id=scan_id, user=request.user)

    try:
        data = json.loads(request.body)
        pages_data = data.get('pages', [])

        # Use Django ORM with two-step approach to avoid unique constraint conflicts
        from django.db import transaction

        with transaction.atomic():
            # Collect pages to update
            page_updates = []
            for page_data in pages_data:
                page_id = page_data.get('page_id')
                new_page_number = page_data.get('page_number')

                # Verify the page belongs to this scan and user
                try:
                    page = ScanPage.objects.get(id=page_id, scan=scan)
                    page_updates.append((page, new_page_number))
                except ScanPage.DoesNotExist:
                    continue

            if page_updates:
                # Step 1: Set all pages to temporary large positive values to avoid conflicts
                for i, (page, new_page_number) in enumerate(page_updates):
                    temp_value = 10000 + i  # Large positive numbers to avoid conflicts
                    page.page_number = temp_value
                    page.save()

                # Step 2: Set to final positive values
                for page, new_page_number in page_updates:
                    page.page_number = new_page_number
                    page.save()

        return JsonResponse({'success': True})

    except (json.JSONDecodeError, KeyError) as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Database error: {str(e)}'}, status=500)

from django.core.management.base import BaseCommand
from django.utils import timezone
from djnote.models import Scan


class Command(BaseCommand):
    help = 'List and optionally delete documents that are due for deletion'

    def add_arguments(self, parser):
        parser.add_argument(
            '--delete',
            action='store_true',
            help='Actually delete the overdue documents (default: just list them)',
        )
        parser.add_argument(
            '--days',
            type=int,
            default=0,
            help='Include documents due within this many days (default: 0 = only overdue)',
        )

    def handle(self, *args, **options):
        now = timezone.now()
        cutoff_date = now + timezone.timedelta(days=options['days'])
        
        # Find documents that are due
        due_documents = Scan.objects.filter(
            scan_type='document',
            due_date__lte=cutoff_date,
            is_archived=False
        ).order_by('due_date')

        if not due_documents.exists():
            self.stdout.write(
                self.style.SUCCESS('No documents are due for deletion.')
            )
            return

        self.stdout.write(f'\nFound {due_documents.count()} document(s) due for deletion:\n')
        
        for doc in due_documents:
            status = "OVERDUE" if doc.is_overdue else "DUE SOON"
            days_overdue = (now - doc.due_date).days if doc.is_overdue else (doc.due_date - now).days
            
            self.stdout.write(
                f"• {doc.title} (ID: {doc.document_id}) - {status}"
            )
            self.stdout.write(
                f"  User: {doc.user.username} | Due: {doc.due_date.strftime('%d.%m.%Y %H:%M')}"
            )
            self.stdout.write(
                f"  Pages: {doc.page_count} | Created: {doc.created_at.strftime('%d.%m.%Y')}"
            )
            if doc.is_overdue:
                self.stdout.write(
                    self.style.ERROR(f"  >>> {days_overdue} days overdue!")
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"  >>> Due in {days_overdue} days")
                )
            self.stdout.write("")

        if options['delete']:
            self.stdout.write(
                self.style.WARNING('\nDeleting overdue documents...')
            )
            
            overdue_docs = due_documents.filter(due_date__lte=now)
            deleted_count = 0
            
            for doc in overdue_docs:
                self.stdout.write(f"Deleting: {doc.title} (ID: {doc.document_id})")
                doc.delete()
                deleted_count += 1
            
            if deleted_count > 0:
                self.stdout.write(
                    self.style.SUCCESS(f'\nDeleted {deleted_count} overdue document(s).')
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS('\nNo overdue documents to delete.')
                )
        else:
            self.stdout.write(
                self.style.WARNING('\nTo actually delete overdue documents, run with --delete flag.')
            )
            self.stdout.write(
                'Example: python manage.py cleanup_due_documents --delete'
            )

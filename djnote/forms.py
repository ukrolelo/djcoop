from django import forms
from django.forms import inlineformset_factory
from .models import Scan, ScanPage


class ScanForm(forms.ModelForm):
    """Form for creating and editing scans"""
    due_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
            'id': 'due-date-input'
        }),
        help_text="Select when this document should be deleted"
    )

    class Meta:
        model = Scan
        fields = ['title', 'scan_type', 'description', 'retention_days', 'due_date']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter scan title'
            }),
            'scan_type': forms.RadioSelect(attrs={
                'class': 'form-check-input',
                'id': 'scan-type-select'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Optional description'
            }),
            'retention_days': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 3650,  # 10 years max
                'placeholder': 'Days to keep (for documents only)'
            })
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make fields conditional
        self.fields['retention_days'].required = False
        self.fields['due_date'].required = False

        # If editing existing scan, populate due_date from due_date field
        if self.instance and self.instance.pk and self.instance.due_date:
            self.fields['due_date'].initial = self.instance.due_date.date()

    def clean(self):
        cleaned_data = super().clean()
        scan_type = cleaned_data.get('scan_type')
        retention_days = cleaned_data.get('retention_days')
        due_date = cleaned_data.get('due_date')

        if scan_type == 'document':
            # For documents, require either retention_days OR due_date
            if not retention_days and not due_date:
                raise forms.ValidationError(
                    "For documents, please specify either retention period (days) or due date."
                )
        else:
            # Clear document-specific fields for notes
            cleaned_data['retention_days'] = None
            cleaned_data['due_date'] = None

        return cleaned_data


class ScanPageForm(forms.ModelForm):
    """Form for individual scan pages"""
    
    class Meta:
        model = ScanPage
        fields = ['image']
        widgets = {
            'image': forms.ClearableFileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*',
                'capture': 'camera'  # Enables camera on mobile
            })
        }


class BulkUploadForm(forms.Form):
    """Form for uploading multiple images at once"""
    # We'll handle multiple files in the template and view
    pass


# Formset for managing multiple scan pages
ScanPageFormSet = inlineformset_factory(
    Scan, 
    ScanPage, 
    form=ScanPageForm,
    extra=1,
    can_delete=True,
    fields=['image']
)

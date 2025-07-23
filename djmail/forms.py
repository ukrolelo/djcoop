from django import forms
from .models import EmailAccount, Task, Email

class EmailAccountForm(forms.ModelForm):
    """Form for creating and editing email accounts"""
    password = forms.CharField(widget=forms.PasswordInput(), required=False)

    class Meta:
        model = EmailAccount
        fields = [
            'name', 'email', 'pop3_server', 'pop3_port',
            'smtp_server', 'smtp_port', 'username', 'password',
            'use_ssl', 'is_default'
        ]
        
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'pop3_server': forms.TextInput(attrs={'class': 'form-control'}),
            'pop3_port': forms.NumberInput(attrs={'class': 'form-control'}),
            'smtp_server': forms.TextInput(attrs={'class': 'form-control'}),
            'smtp_port': forms.NumberInput(attrs={'class': 'form-control'}),
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'password': forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Leave blank to keep current password'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # For editing existing accounts, make password not required
        if self.instance and self.instance.pk:
            self.fields['password'].required = False
            self.fields['password'].help_text = "Leave blank to keep current password"
        else:
            self.fields['password'].required = True

class ComposeEmailForm(forms.Form):
    """Form for composing a new email"""
    to = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Recipient(s) - separate multiple addresses with commas'})
    )
    cc = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'CC - separate multiple addresses with commas'}),
        required=False
    )
    bcc = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'BCC - separate multiple addresses with commas'}),
        required=False
    )
    subject = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Subject'})
    )
    body = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 12}),
        required=False
    )
    attachments = forms.FileField(
        widget=forms.ClearableFileInput(attrs={'class': 'form-control'}),
        required=False
    )

class TaskForm(forms.ModelForm):
    """Form for creating and editing tasks"""
    due_date = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
        required=False
    )
    
    class Meta:
        model = Task
        fields = ['title', 'description', 'related_email', 'status', 'priority', 'due_date']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'related_email': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
        }

class TaskUpdateForm(forms.ModelForm):
    """Form for updating task status"""
    class Meta:
        model = Task
        fields = ['status']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-select'})
        }

class EmailSearchForm(forms.Form):
    """Form for searching emails"""
    query = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Search emails...'}),
        required=False
    )
    folder = forms.CharField(
        widget=forms.HiddenInput(),
        required=False
    )
    from_date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        required=False
    )
    to_date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        required=False
    )
    has_attachment = forms.BooleanField(
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        required=False
    )

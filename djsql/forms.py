from django import forms
from .models import DatabaseServer, DatabaseUser

class DatabaseServerForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(render_value=True))
    
    class Meta:
        model = DatabaseServer
        fields = ['name', 'host', 'port', 'username', 'password', 'description', 'is_active']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def clean_port(self):
        port = self.cleaned_data.get('port')
        if port < 1 or port > 65535:
            raise forms.ValidationError("Port must be between 1 and 65535")
        return port

class DatabaseUserForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(render_value=True))
    
    class Meta:
        model = DatabaseUser
        fields = ['server', 'username', 'password', 'host', 'user_type']
        widgets = {
            'host': forms.TextInput(attrs={'placeholder': 'localhost, %, IP address'}),
        }

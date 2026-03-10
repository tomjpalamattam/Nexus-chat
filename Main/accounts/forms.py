from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User, APIConfiguration


class RegisterForm(UserCreationForm):
    class Meta:
        model = User
        fields = ('username', 'password1', 'password2')


class CreateUserForm(UserCreationForm):
    email = forms.EmailField(required=False)

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')


class APIConfigForm(forms.ModelForm):
    api_key = forms.CharField(
        widget=forms.PasswordInput(render_value=True),
    )

    class Meta:
        model = APIConfiguration
        fields = ('label', 'provider', 'api_key', 'base_url', 'model_name', 'is_default')
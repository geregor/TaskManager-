from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import get_user_model

User = get_user_model()

class EmployeeLoginForm(AuthenticationForm):
    username = forms.EmailField(
        label="Почта",
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Введите почту'
        })
    )
    password = forms.CharField(
        label="Пароль",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Введите пароль'
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = 'Email'
from django import forms
from django.contrib.auth.models import User
from .models import Device, Customer


class DeviceForm(forms.ModelForm):
    class Meta:
        model = Device
        fields = ["name", "ip", "port"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Название устройства"}),
            "ip": forms.TextInput(attrs={"class": "form-control", "placeholder": "IP адрес"}),
            "port": forms.NumberInput(attrs={"class": "form-control", "placeholder": "Порт"}),
        }


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ["photo", "bio"]
        widgets = {
            "bio": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "О себе"}),
        }


class UserRegisterForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Пароль"}))
    password2 = forms.CharField(label="Повторите пароль", widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Повторите пароль"}))

    class Meta:
        model = User
        fields = ["username", "email"]
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control", "placeholder": "Логин"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "Email (необязательно)", "required": False}),
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password") != cleaned.get("password2"):
            raise forms.ValidationError("Пароли не совпадают")
        return cleaned


class LoginForm(forms.Form):
    username = forms.CharField(widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Логин"}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Пароль"}))


class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["username", "email"]
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control", "placeholder": "Логин"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "Email"}),
        }

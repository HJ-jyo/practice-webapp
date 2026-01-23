from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from .models import Task, Profile

class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ('username', 'email')

class CustomAuthenticationForm(AuthenticationForm):
    remember_me = forms.BooleanField(required=False, widget=forms.CheckboxInput())

class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        # ★ category を削除しました
        fields = ['title', 'description', 'due_date']
        
        widgets = {
            'due_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'description': forms.Textarea(attrs={'rows': 4, 'placeholder': 'タスクの詳細やメモを入力...'}),
        }

class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['icon', 'bio']
        widgets = {
            'bio': forms.Textarea(attrs={'rows': 4, 'placeholder': '自己紹介...'}),
        }

class VerificationCodeForm(forms.Form):
    code = forms.CharField(
        label='認証コード',
        max_length=6,
        widget=forms.TextInput(attrs={'placeholder': '6桁のコードを入力', 'autofocus': 'autofocus'})
    )
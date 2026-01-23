from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from .models import Task, Profile

class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ('username', 'email')

class CustomAuthenticationForm(AuthenticationForm):
    """
    ログインフォーム
    デザインはテンプレート側で制御するため、ここは標準機能の継承のみ
    """
    pass

class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ['title', 'description', 'due_date', 'category']
        
        # カレンダー入力などを有効にする設定
        widgets = {
            'due_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'description': forms.Textarea(attrs={'rows': 4, 'placeholder': 'タスクの詳細やメモを入力...'}),
        }

class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        # ▼▼▼ ここに 'bio' を追加することで、画面に入力欄が表示されます ▼▼▼
        fields = ['icon', 'bio']
        
        widgets = {
            'bio': forms.Textarea(attrs={
                'rows': 4, 
                'placeholder': '趣味や好きなこと、チームへの一言などを書きましょう...'
            }),
        }
from django import forms
from .models import Task, Comment, OneTimePassword, Category, Profile
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm

class UserUpdateForm(forms.ModelForm):
    email = forms.EmailField(label="メールアドレス")

    class Meta:
        model = User
        fields = ['username', 'email']
        labels = {
            'username': 'ユーザー名',
        }

class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['bio']
        widgets = {
            'bio': forms.Textarea(attrs={'rows': 4, 'placeholder': '自己紹介文を入力してください'}),
        }

class SignUpForm(UserCreationForm):
    class Meta:
        model = User
        fields = ('username','email')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = True
        self.fields['email'].label = "メールアドレス"
        self.fields['email'].widget.attrs.update({'class': 'form-control', 'placeholder': 'example@email.com'})
        self.fields['username'].widget.attrs.update({'class': 'form-control', 'placeholder': 'ユーザー名'})
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("このメールアドレスは既に登録されています。")
        return email


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control','placeholder': '例:仕事、買い物、緊急'}),
        }
        
class TaskForm(forms.ModelForm):
    # Googleカレンダーに追加するかどうかのチェックボックス
    add_to_gcal = forms.BooleanField(
        required=False, 
        label="Googleカレンダーに追加用リンクを作成する",
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    class Meta:
        model = Task
        fields = ['title', 'description', 'due_date', 'status', 'repeat_mode', 'category']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'タスク名'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'due_date': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'repeat_mode': forms.Select(attrs={'class': 'form-select'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, user=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['due_date'].input_formats = (
            '%Y-%m-%dT%H:%M',
            '%Y-%m-%dT%H:%M:%S', 
        )
        if user:
            self.fields['category'].queryset = Category.objects.filter(user=user)

class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['text']
        widgets = {
            'text': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'コメントを入力...'}),
        }

class EmailLoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = "メールアドレス"
        self.fields['username'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'example@email.com',
            'autofocus': True
        })
        self.fields['password'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'パスワード'
        })

class VerificationCodeForm(forms.Form):
    code = forms.CharField(
        label="認証コード",
        max_length=6,
        widget=forms.TextInput(attrs={
            'class': 'form-control text-center',
            'placeholder': '000000',
            'style': 'font-size: 1.5rem; letter-spacing: 0.5em;'
        })
    )

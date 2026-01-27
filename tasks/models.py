from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import random
import string

# --- プロフィール ---
class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    bio = models.TextField(blank=True, null=True, verbose_name='自己紹介')
    icon = models.ImageField(upload_to='icons/', blank=True, null=True, verbose_name='アイコン')

    def __str__(self):
        return self.user.username

# --- タスク ---
class Task(models.Model):
    REPEAT_CHOICES = [
        ('none', 'なし'),
        ('daily', '毎日'),
        ('weekly', '毎週'),
        ('monthly', '毎月'),
    ]
    STATUS_CHOICES = [
        ('todo', '未着手'),
        ('doing', '進行中'),
        ('done', '完了'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_tasks')
    title = models.CharField(max_length=100, verbose_name='タイトル')
    description = models.TextField(blank=True, null=True, verbose_name='詳細')
    due_date = models.DateTimeField(blank=True, null=True, verbose_name='期限')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='todo')
    
    # 担当者（複数人）
    assigned_users = models.ManyToManyField(User, related_name='assigned_tasks', blank=True)
    
    # 繰り返し設定
    repeat_mode = models.CharField(max_length=10, choices=REPEAT_CHOICES, default='none', verbose_name='繰り返し')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

# --- 招待機能 ---
class Invitation(models.Model):
    STATUS_CHOICES = [
        ('pending', '保留中'),
        ('accepted', '承諾'),
        ('declined', '拒否'),
    ]
    task = models.ForeignKey(Task, on_delete=models.CASCADE)
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_invitations')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_invitations')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.sender} -> {self.recipient} ({self.task})"

# --- コメント機能 ---
class Comment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user}: {self.content[:20]}"

# --- 2段階認証用ワンタイムパスワード ---
class OneTimePassword(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    code = models.CharField(max_length=6, blank=True)
    created_at = models.DateTimeField(auto_now=True) # 更新されるたびに時刻更新

    def generate_code(self):
        code = ''.join(random.choices(string.digits, k=6))
        self.code = code
        self.save()
        return code

    def is_valid(self):
        # 10分以内なら有効
        return timezone.now() < self.created_at + timezone.timedelta(minutes=10)
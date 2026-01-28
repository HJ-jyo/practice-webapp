import uuid
import urllib.parse
import random
from datetime import timedelta
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

# --- 1. プロフィール ---
class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    bio = models.TextField(max_length=500, blank=True, null=True)
    icon = models.ImageField(upload_to='avatars/', blank=True, null=True)

    def __str__(self): return self.user.username

# --- 2. タスク ---
class Task(models.Model):
    # タスク自体のステータス（自動計算されるが、完了フラグとして保持）
    STATUS_CHOICES = (('active', '進行中'), ('done', '完了'))
    
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    due_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_tasks')
    
    # ★重要変更: throughオプションを使って、メンバーごとのステータスを管理する
    assigned_users = models.ManyToManyField(User, related_name='assigned_tasks', blank=True, through='TaskAssignment')
    
    token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self): return self.title

# --- ★新規: メンバーごとの進捗管理 ---
class TaskAssignment(models.Model):
    STATUS_CHOICES = (
        ('todo', '未着手'),
        ('doing', '進行中'),
        ('done', '完了'),
    )
    task = models.ForeignKey(Task, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='todo')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('task', 'user')

# --- 3. その他（招待など） ---
class Invitation(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE)
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_invitations')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_invitations')
    status = models.CharField(max_length=10, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

class Comment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    attachment = models.FileField(upload_to='attachments/', blank=True, null=True, verbose_name='添付ファイル')
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.user}: {self.content[:20]}"

class OneTimePassword(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now=True)
    def is_valid(self): return self.created_at >= timezone.now() - timedelta(minutes=10)
    def generate_code(self):
        self.code = str(random.randint(100000, 999999))
        self.save()
        return self.code
import uuid
import urllib.parse
import random
from datetime import timedelta
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.db.models.signals import post_save
from django.dispatch import receiver

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    bio = models.TextField(max_length=500, blank=True, verbose_name="自己紹介")

    def __str__(self):
        return f"{self.user.username}のプロフィール"

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()

class Category(models.Model):
    name = models.CharField(max_length=50, verbose_name="カテゴリ名")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Task(models.Model):
    # ステータスの選択肢
    STATUS_CHOICES = (
        ('todo', '未着手'),
        ('doing', '進行中'),
        ('done', '完了'),
    )

    # 繰り返し設定の選択肢
    REPEAT_CHOICES = [
        ('none', '繰り返しなし'),
        ('daily', '毎日'),
        ('weekly', '毎週'),
        ('monthly', '毎月'),
    ]

    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="カテゴリ")


    title = models.CharField(max_length=100, verbose_name=_("Task Name"))
    description = models.TextField(blank=True, verbose_name=_("Description"))
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='todo',
        verbose_name="状態"
    )
    due_date = models.DateTimeField(null=True, blank=True, verbose_name="期限")
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="作成者")
    
    # 参加者（承認されたユーザーが入る）
    participants = models.ManyToManyField(User, verbose_name="参加者", blank=True, related_name='joined_tasks')
    
    token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    repeat_mode = models.CharField(
        max_length=10,
        choices=REPEAT_CHOICES,
        default='none',
        verbose_name='繰り返し設定',
    )

    def __str__(self):
        return self.title

    @property
    def is_overdue(self):
        """期限切れかどうかを判定"""
        if self.due_date and timezone.now() > self.due_date:
            return True
        return False
    
    def get_gcal_link(self):
        """Googleカレンダー追加用リンク生成"""
        base_url = "https://www.google.com/calendar/render?action=TEMPLATE"
        
        text = f"{self.title}(kanban)"
        details = f"{self.description}\n\n担当: {self.user.username}"

        if self.due_date:
            start_str = self.due_date.strftime('%Y%m%dT%H%M00')
            end_date = self.due_date + timedelta(hours=1)
            end_str = end_date.strftime('%Y%m%dT%H%M00')
            dates = f"{start_str}/{end_str}"
        else:
            return ""
        
        params = {
            'text': text,
            'details': details,
            'dates': dates,
        }
        return f"{base_url}&{urllib.parse.urlencode(params)}"

class Comment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    text = models.TextField(verbose_name="コメント内容")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.text[:20]

# --- メッセージボード用モデル ---
class TaskInvitation(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='invitations')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_invitations')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_invitations')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('task', 'recipient') # 同じタスクに二重招待できないようにする

    def __str__(self):
        return f"{self.sender} invited {self.recipient} to {self.task}"
    
class OneTimePassword(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} : {self.code}"

    def is_valid(self):
        return self.created_at >= timezone.now() - timedelta(minutes=10)
    
    def generate_code(self):
        self.code = str(random.randint(100000, 999999))
        self.save()
        return self.code
    

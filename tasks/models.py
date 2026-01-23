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

# --- 1. プロフィール ---
class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    bio = models.TextField(max_length=500, blank=True, null=True, verbose_name="自己紹介")
    icon = models.ImageField(upload_to='avatars/', blank=True, null=True)

    def __str__(self):
        return f"{self.user.username}のプロフィール"

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()

# --- 2. カテゴリ ---
class Category(models.Model):
    name = models.CharField(max_length=50, verbose_name="カテゴリ名")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

# --- 3. タスク ---
class Task(models.Model):
    STATUS_CHOICES = (
        ('todo', '未着手'),
        ('doing', '進行中'),
        ('done', '完了'),
    )

    REPEAT_CHOICES = [
        ('none', 'なし'),
        ('daily', '毎日'),
        ('weekly', '毎週'),
        ('monthly', '毎月'),
    ]

    title = models.CharField(max_length=100, verbose_name="タスク名")
    description = models.TextField(blank=True, verbose_name="詳細")
    
    # 期限
    due_date = models.DateTimeField(null=True, blank=True, verbose_name="期限")
    
    # ステータス
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='todo',
        verbose_name="状態"
    )
    
    # カテゴリ
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="カテゴリ")
    
    # 作成者 (related_nameを統一)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_tasks', verbose_name="作成者")
    
    # 参加メンバー
    assigned_users = models.ManyToManyField(User, related_name='assigned_tasks', blank=True, verbose_name="参加メンバー")
    
    # 繰り返し設定
    repeat_mode = models.CharField(
        max_length=10,
        choices=REPEAT_CHOICES,
        default='none',
        verbose_name='繰り返し設定',
    )
    
    # 共有用トークン
    token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    @property
    def is_overdue(self):
        """期限切れ判定"""
        if self.due_date and timezone.now() > self.due_date and self.status != 'done':
            return True
        return False
    
    def get_gcal_link(self):
        """Googleカレンダー用リンク"""
        if not self.due_date:
            return ""
        base_url = "https://www.google.com/calendar/render?action=TEMPLATE"
        text = f"{self.title} (Kanban)"
        details = f"{self.description}\n\n担当: {self.user.username}"
        start_str = self.due_date.strftime('%Y%m%dT%H%M00')
        end_date = self.due_date + timedelta(hours=1)
        end_str = end_date.strftime('%Y%m%dT%H%M00')
        dates = f"{start_str}/{end_str}"
        params = {'text': text, 'details': details, 'dates': dates}
        return f"{base_url}&{urllib.parse.urlencode(params)}"

# --- 4. コメント (修正: HTMLに合わせてフィールド名を統一) ---
class Comment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='comments')
    # author -> user に変更 (HTML側が user を参照しているため)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    # text -> content に変更 (HTML側が content を参照しているため)
    content = models.TextField(verbose_name="コメント内容")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.content[:20]

# --- 5. 招待 (修正: Invitationに統一し、ステータスを追加) ---
class Invitation(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='invitations')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_invitations')
    # 招待相手 (ユーザーが存在することを前提とします)
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_invitations')
    
    # ▼▼▼ これが足りていませんでした！ ▼▼▼
    STATUS_CHOICES = (
        ('pending', '保留中'),
        ('accepted', '承認'),
        ('declined', '拒否'),
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # TaskInvitation -> Invitation に戻します
        unique_together = ('task', 'recipient') 

    def __str__(self):
        return f"{self.sender} invited {self.recipient} to {self.task}"
    
# --- 6. 2段階認証コード ---
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
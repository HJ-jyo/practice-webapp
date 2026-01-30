from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
import random
from datetime import timedelta

User = get_user_model()

# === ユーザープロフィール ===
class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    bio = models.TextField(blank=True, null=True)
    icon = models.ImageField(upload_to='icons/', blank=True, null=True)
    verification_code = models.CharField(max_length=6, blank=True, null=True) # 新規登録時の認証用

    def __str__(self):
        return self.user.username

# === 2段階認証用ワンタイムパスワード ===
class OneTimePassword(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    code = models.CharField(max_length=6)
    updated_at = models.DateTimeField(auto_now=True)

    def generate_code(self):
        self.code = str(random.randint(100000, 999999))
        self.save()
        return self.code

    def is_valid(self):
        # 10分以内なら有効
        return timezone.now() - self.updated_at < timedelta(minutes=10)

# === タスク本体 ===
class Task(models.Model):
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    due_date = models.DateTimeField(blank=True, null=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)  # 作成者
    created_at = models.DateTimeField(auto_now_add=True)
    # チーム用フィールド (ManyToManyFieldはTaskAssignmentで代用するため削除しても良いが、互換性のため残す場合あり)
    assigned_users = models.ManyToManyField(User, related_name='assigned_tasks', blank=True)

    def __str__(self):
        return self.title

    def progress_percent(self):
        total_subtasks = self.subtasks.count()
        if total_subtasks == 0:
            return 0
        done_subtasks = self.subtasks.filter(is_done=True).count()
        return int((done_subtasks / total_subtasks) * 100)
    
    def is_overdue(self):
        if self.due_date and self.progress_percent() < 100:
            return timezone.now() > self.due_date
        return False

    # 期限までの残り日数
    def remaining_days(self):
        if not self.due_date:
            return None
        delta = self.due_date.date() - timezone.now().date()
        return delta.days

    # カードの色判定
    def color_class(self):
        days = self.remaining_days()
        if days is None: return ""
        if days < 0: return "urgency-red"
        elif days <= 3: return "urgency-yellow"
        else: return "urgency-green"


# === ★チャットスレッド（チャンネル） ===
class ChatThread(models.Model):
    task = models.ForeignKey(Task, related_name='threads', on_delete=models.CASCADE)
    name = models.CharField(max_length=50, default='メイン')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


# === タスクメンバー管理 ===
class TaskAssignment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, default='todo')
    
    # ★追加機能: ロールと参加日
    role_name = models.CharField(max_length=50, blank=True, null=True)
    joined_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.task.title} - {self.user.username}"


# === チャットコメント ===
class Comment(models.Model):
    task = models.ForeignKey(Task, related_name='comments', on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    attachment = models.FileField(upload_to='attachments/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # ★追加機能: スレッドとメッセージタイプ
    thread = models.ForeignKey(ChatThread, related_name='comments', on_delete=models.CASCADE, null=True, blank=True)
    message_type = models.CharField(max_length=20, default='normal')

    def __str__(self):
        return f"{self.user.username}: {self.content[:20]}"


# === ★WBS（サブタスク） ===
class SubTask(models.Model):
    task = models.ForeignKey(Task, related_name='subtasks', on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    is_done = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


# === 招待機能 ===
class Invitation(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE)
    sender = models.ForeignKey(User, related_name='sent_invitations', on_delete=models.CASCADE)
    recipient = models.ForeignKey(User, related_name='received_invitations', on_delete=models.CASCADE)
    status = models.CharField(max_length=20, default='pending') # pending, accepted, declined
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Invite from {self.sender} to {self.recipient}"
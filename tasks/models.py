from django.db import models
from django.contrib.auth.models import User
import uuid
from django.utils import timezone

class Task(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    due_date = models.DateTimeField(blank=True, null=True)
    status = models.CharField(
        max_length=20, 
        choices=[('active', 'Active'), ('done', 'Done')], 
        default='active'
    )
    assigned_users = models.ManyToManyField(User, related_name='assigned_tasks', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title
    
    def progress_percent(self):
        total_subtasks = self.subtasks.count()
        if total_subtasks == 0:
            # サブタスクがない場合は、ステータスから簡易計算（任意）
            # ここでは0%としますが、必要なら既存のロジックを維持してください
            return 0 
        done_subtasks = self.subtasks.filter(is_done=True).count()
        return int((done_subtasks / total_subtasks) * 100)

class TaskAssignment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    status = models.CharField(
        max_length=20,
        choices=[('todo', 'Todo'), ('doing', 'Doing'), ('done', 'Done')],
        default='todo'
    )
    role_name = models.CharField(max_length=50, blank=True, null=True)
    joined_at = models.DateField(auto_now_add=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        unique_together = ('task', 'user')

class Comment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField(blank=True) 
    # ★追加: ファイル添付
    attachment = models.FileField(upload_to='attachments/', blank=True, null=True, verbose_name='添付ファイル')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user}: {self.content[:20]}"

# 以下、Invitation, OneTimePassword, Profile は変更ないのでそのまま残すか、
# 必要なら以前のコードを使ってください（ここでは省略しません）
class Invitation(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE)
    sender = models.ForeignKey(User, related_name='sent_invitations', on_delete=models.CASCADE)
    recipient = models.ForeignKey(User, related_name='received_invitations', on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=[('pending', 'Pending'), ('accepted', 'Accepted'), ('declined', 'Declined')], default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

class OneTimePassword(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now=True)
    def generate_code(self):
        self.code = str(uuid.uuid4().int)[:6]
        self.save()
        return self.code
    def is_valid(self):
        from django.utils import timezone
        return self.created_at >= timezone.now() - timezone.timedelta(minutes=10)

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    bio = models.TextField(max_length=500, blank=True)
    icon = models.ImageField(upload_to='icons/', blank=True, null=True)
    def __str__(self): return self.user.username

class SubTask(models.Model):
    task = models.ForeignKey(Task, related_name='subtasks', on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    is_done = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title
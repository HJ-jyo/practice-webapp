from datetime import timedelta
from dateutil.relativedelta import relativedelta
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.core.mail import send_mail
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
import json

from .models import Task, Invitation, Comment, OneTimePassword, Profile
from .forms import CustomUserCreationForm, CustomAuthenticationForm, TaskForm, ProfileForm, VerificationCodeForm

# --- 認証関連 ---

class SignUpView(CreateView):
    form_class = CustomUserCreationForm
    template_name = 'registration/signup.html'
    success_url = reverse_lazy('login')

    def form_valid(self, form):
        user = form.save()
        Profile.objects.get_or_create(user=user)
        messages.success(self.request, 'アカウント作成が完了しました！')
        return super().form_valid(form)

class CustomLoginView(LoginView):
    authentication_form = CustomAuthenticationForm
    template_name = 'registration/login.html'

    def form_valid(self, form):
        user = form.get_user()
        self.request.session['pre_2fa_user_id'] = user.id
        if self.request.POST.get('remember_me'):
            self.request.session.set_expiry(1209600)

        otp, _ = OneTimePassword.objects.get_or_create(user=user)
        code = otp.generate_code()
        
        send_mail(
            "【Kanban】認証コード",
            f"コード: {code}\n有効期限は10分です。",
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=True
        )
        return redirect('verify_code')

def verify_code_view(request):
    user_id = request.session.get('pre_2fa_user_id')
    if not user_id: return redirect('login')
    
    user = get_object_or_404(User, id=user_id)
    
    if request.method == 'POST':
        form = VerificationCodeForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data.get('code')
            try:
                otp = OneTimePassword.objects.get(user=user)
                if otp.code == code and otp.is_valid():
                    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                    otp.code = "" 
                    otp.save()
                    if 'pre_2fa_user_id' in request.session:
                        del request.session['pre_2fa_user_id']
                    return redirect('board')
                else:
                    messages.error(request, 'コードが間違っているか、期限切れです。')
            except OneTimePassword.DoesNotExist:
                messages.error(request, 'エラーが発生しました。')
    else:
        form = VerificationCodeForm()
            
    return render(request, 'registration/verify_code.html', {'form': form, 'email': user.email})

def index(request):
    return redirect('board') if request.user.is_authenticated else redirect('login')


# --- メイン機能 (大幅改修) ---

@login_required
def board(request):
    current_user = request.user
    
    # 自分が関わっているタスクを取得
    tasks = Task.objects.filter(Q(user=current_user) | Q(assigned_users=current_user)).distinct()

    # 検索フィルタ
    query = request.GET.get('q')
    if query:
        tasks = tasks.filter(Q(title__icontains=query) | Q(description__icontains=query))

    # ★改修: 期限が近い順（昇順）に並び替え
    tasks = tasks.order_by('due_date') 

    # ★改修: タスクに「緊急度」「残り日数」「進捗」の情報を付与する
    today = timezone.now().date()
    
    # Pythonオブジェクトとして処理するためにリスト化して属性を追加
    enhanced_tasks = []
    for task in tasks:
        # 1. 期限・緊急度ロジック
        if not task.due_date:
            task.urgency = 'none'
            task.remaining_days = None
        else:
            delta = (task.due_date.date() - today).days
            task.remaining_days = delta

            if delta <= 1:
                task.urgency = 'high'   # 赤: 1日前以内
            elif delta <= 3:
                task.urgency = 'medium' # 黄: 3日前以内
            elif delta >= 7:
                task.urgency = 'low'    # 緑: 1週間以上
            else:
                task.urgency = 'normal' # その他

        # 2. 進捗パーセンテージ（簡易ロジック）
        if task.status == 'todo':
            task.progress_percent = 0
        elif task.status == 'doing':
            task.progress_percent = 50
        else:
            task.progress_percent = 100
        
        enhanced_tasks.append(task)
    
    # ステータスごとに振り分け
    tasks_todo = [t for t in enhanced_tasks if t.status == 'todo']
    tasks_doing = [t for t in enhanced_tasks if t.status == 'doing']
    tasks_done = [t for t in enhanced_tasks if t.status == 'done']
    
    context = {
        'tasks_todo': tasks_todo,
        'tasks_doing': tasks_doing,
        'tasks_done': tasks_done,
        'total_tasks': tasks.count(),
        'completed_tasks': tasks.filter(status='done').count(),
        'query': query,
    }
    return render(request, 'tasks/board.html', context)


# --- Ajax API (新規追加) ---

@login_required
@require_POST
def api_move_task(request):
    """
    Ajax通信でタスクのステータスを変更するAPI
    """
    try:
        data = json.loads(request.body)
        task_id = data.get('task_id')
        new_status = data.get('status')

        task = get_object_or_404(Task, id=task_id)
        
        # 権限チェック
        if task.user != request.user and request.user not in task.assigned_users.all():
            return JsonResponse({'status': 'error', 'message': 'Permission denied'}, status=403)

        if new_status in ['todo', 'doing', 'done']:
            task.status = new_status
            task.save()
            return JsonResponse({'status': 'success', 'new_status': new_status})
        
        return JsonResponse({'status': 'error', 'message': 'Invalid status'}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


# --- 招待リンク機能 (新規追加) ---

@login_required
def join_task_via_link(request, pk):
    """
    招待リンク（URL）を踏むだけでタスクに参加できるビュー
    """
    task = get_object_or_404(Task, id=pk)
    
    # すでに参加している場合はそのままボードへ
    if request.user == task.user or request.user in task.assigned_users.all():
        messages.info(request, "すでにこのタスクに参加しています。")
        return redirect('board')
    
    # 参加処理
    task.assigned_users.add(request.user)
    messages.success(request, f"タスク「{task.title}」に参加しました！")
    return redirect('board')


# --- 既存のタスク操作 (フォールバック用) ---

@login_required
def move_to_doing(request, pk):
    task = get_object_or_404(Task, id=pk)
    if task.user != request.user and request.user not in task.assigned_users.all():
        return redirect('board')
    task.status = 'doing' 
    task.save()
    return redirect('board')

@login_required
def move_to_done(request, pk):
    task = get_object_or_404(Task, id=pk)
    if task.user != request.user and request.user not in task.assigned_users.all():
        return redirect('board')
        
    task.status = 'done'
    task.save()
    
    if task.repeat_mode != 'none' and task.due_date:
        next_due_date = task.due_date
        if task.repeat_mode == 'daily': next_due_date += timedelta(days=1)
        elif task.repeat_mode == 'weekly': next_due_date += timedelta(weeks=1)
        elif task.repeat_mode == 'monthly': next_due_date += relativedelta(months=1)
        
        new_task = Task.objects.create(
            user=task.user,
            title=task.title,
            description=task.description,
            due_date=next_due_date,
            status='todo',
            repeat_mode=task.repeat_mode
        )
        for member in task.assigned_users.all():
            new_task.assigned_users.add(member)

        messages.success(request, f"タスク完了！次回分（{next_due_date.strftime('%m/%d')}）を作成しました。")
    else:
        messages.success(request, "タスクを完了しました！")
        
    return redirect('board')

@login_required
def delete_done_tasks(request):
    if request.method == 'POST':
        deleted_count, _ = Task.objects.filter(user=request.user, status='done').delete()
        assigned_done_tasks = Task.objects.filter(assigned_users=request.user, status='done')
        left_count = 0
        for task in assigned_done_tasks:
            if task.user != request.user:
                task.assigned_users.remove(request.user)
                left_count += 1
        
        total = deleted_count + left_count
        if total > 0:
            messages.success(request, f"{total}件の完了タスクを整理しました。")
    return redirect('board')

# --- CBV (CRUD) ---

class TaskCreateView(LoginRequiredMixin, CreateView):
    model = Task
    form_class = TaskForm
    template_name = 'tasks/task_form.html'
    success_url = reverse_lazy('board')

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)

class TaskUpdateView(LoginRequiredMixin, UpdateView):
    model = Task
    form_class = TaskForm
    template_name = 'tasks/task_form.html'
    success_url = reverse_lazy('board')
    def get_queryset(self):
        return Task.objects.filter(Q(user=self.request.user) | Q(assigned_users=self.request.user)).distinct()

class TaskDeleteView(LoginRequiredMixin, DeleteView):
    model = Task
    template_name = 'tasks/task_confirm_delete.html'
    success_url = reverse_lazy('board')
    def get_queryset(self):
        return Task.objects.filter(user=self.request.user)

# --- プロフィール ---

@login_required
def profile_view(request):
    Profile.objects.get_or_create(user=request.user)
    user_tasks = Task.objects.filter(Q(user=request.user) | Q(assigned_users=request.user)).distinct()
    context = {
        'tasks_count': user_tasks.count(),
        'done_count': user_tasks.filter(status='done').count(),
    }
    return render(request, 'tasks/profile.html', context)

@login_required
def profile_edit(request):
    profile, created = Profile.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        form = ProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'プロフィールを更新しました。')
            return redirect('profile')
    else:
        form = ProfileForm(instance=profile)
    return render(request, 'tasks/profile_edit.html', {'form': form})

# --- 招待 & チャット ---

@login_required
def invite_user(request, pk):
    task = get_object_or_404(Task, id=pk)
    if task.user != request.user and request.user not in task.assigned_users.all():
        messages.error(request, "権限がありません。")
        return redirect('board')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        try:
            user_to_invite = User.objects.get(username=username)
            if user_to_invite == request.user:
                messages.warning(request, "自分自身は招待できません。")
            elif user_to_invite == task.user or user_to_invite in task.assigned_users.all():
                messages.warning(request, "既に参加しています。")
            elif Invitation.objects.filter(task=task, recipient=user_to_invite).exists():
                messages.info(request, "既に招待済みです。")
            else:
                Invitation.objects.create(task=task, sender=request.user, recipient=user_to_invite, status='pending')
                messages.success(request, f"{username} に招待を送りました。")
        except User.DoesNotExist:
            messages.error(request, f"ユーザー {username} は見つかりません。")
            
    return redirect('task_edit', pk=task.id)

@login_required
def invitation_list(request):
    invitations = Invitation.objects.filter(recipient=request.user, status='pending').order_by('-created_at')
    return render(request, 'tasks/invitation_list.html', {'invitations': invitations})

@login_required
def respond_invitation(request, pk, response):
    invitation = get_object_or_404(Invitation, id=pk, recipient=request.user)
    if response == 'accepted':
        invitation.status = 'accepted'
        invitation.task.assigned_users.add(request.user)
        invitation.save()
        messages.success(request, f"{invitation.task.title} に参加しました！")
    elif response == 'declined':
        invitation.status = 'declined'
        invitation.save()
    return redirect('invitation_list')

@login_required
def leave_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    if request.user in task.assigned_users.all():
        task.assigned_users.remove(request.user)
        messages.success(request, "タスクから退出しました。")
    return redirect('board')

@login_required
def add_comment(request, pk):
    task = get_object_or_404(Task, id=pk)
    if request.method == 'POST':
        content = request.POST.get('content') 
        if content:
            Comment.objects.create(task=task, user=request.user, content=content)
    return redirect('task_edit', pk=pk)

@login_required
def remove_member(request, pk):
    task = get_object_or_404(Task, id=pk)
    
    if task.user != request.user:
        messages.error(request, "メンバーを削除できるのはタスク作成者のみです。")
        return redirect('task_edit', pk=pk)

    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        if user_id:
            try:
                target_user = User.objects.get(id=user_id)
                if target_user == task.user:
                    messages.warning(request, "オーナー自身を削除することはできません。")
                    return redirect('task_edit', pk=pk)

                if target_user in task.assigned_users.all():
                    task.assigned_users.remove(target_user)
                    Invitation.objects.filter(task=task, recipient=target_user).delete()
                    messages.success(request, f"{target_user.username} をタスクから削除しました。")
                else:
                    messages.warning(request, "そのユーザーは既に参加していません。")
            except User.DoesNotExist:
                messages.error(request, "対象のユーザーが見つかりませんでした。")
    
    return redirect('task_edit', pk=pk)
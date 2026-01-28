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

from .models import Task, TaskAssignment, Invitation, Comment, OneTimePassword, Profile
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
        
        # ★修正箇所: fail_silently=False に変更してエラーを表示させる
        send_mail(
            "【Kanban】認証コード",
            f"コード: {code}\n有効期限は10分です。",
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False 
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


# --- メイン機能 (ボード・完了タスク) ---

def enhance_task_data(task, current_user):
    """タスクに表示用データ（緊急度、進捗率、自分のステータス）を付与するヘルパー関数"""
    today = timezone.now().date()
    
    # 1. 期限チェック (赤・黄・緑)
    if task.due_date:
        delta = (task.due_date.date() - today).days
        task.remaining_days = delta
        if delta <= 1:
            task.color_class = 'urgency-red'     # 1日前〜期限切れ
        elif delta <= 3:
            task.color_class = 'urgency-yellow'  # 3日前
        elif delta >= 7:
            task.color_class = 'urgency-green'   # 1週間以上
        else:
            task.color_class = 'urgency-green'   # その他（4-6日）
    else:
        task.remaining_days = None
        task.color_class = 'urgency-green'

    # 2. 進捗率計算 (メンバーの完了数 / 全メンバー数)
    # TaskAssignmentモデルを使います
    assignments = TaskAssignment.objects.filter(task=task)
    total_members = assignments.count()
    done_members = assignments.filter(status='done').count()
    
    if total_members > 0:
        task.progress_percent = int((done_members / total_members) * 100)
    else:
        task.progress_percent = 0

    # 3. 自分のステータスを取得
    my_assign = assignments.filter(user=current_user).first()
    task.my_status = my_assign.status if my_assign else 'none'
    
    # メンバーリスト（アイコン表示用）
    task.member_list = assignments

    return task

@login_required
def board(request):
    """
    メインボード: 「完了していない(active)」タスクのみを表示
    """
    # 自分が関わるタスクを取得
    tasks = Task.objects.filter(
        Q(user=request.user) | Q(assigned_users=request.user)
    ).filter(status='active').distinct().order_by('due_date') # 期限が近い順

    # 検索フィルタ
    query = request.GET.get('q')
    if query:
        tasks = tasks.filter(Q(title__icontains=query) | Q(description__icontains=query))

    # データ加工
    enhanced_tasks = [enhance_task_data(t, request.user) for t in tasks]

    return render(request, 'tasks/board.html', {
        'tasks': enhanced_tasks,
        'query': query,
        'view_type': 'board' # テンプレートでの表示切り替え用
    })

@login_required
def done_tasks_view(request):
    """
    完了タスク専用画面: 「完了(done)」タスクのみを表示
    """
    tasks = Task.objects.filter(
        Q(user=request.user) | Q(assigned_users=request.user)
    ).filter(status='done').distinct().order_by('-updated_at')

    enhanced_tasks = [enhance_task_data(t, request.user) for t in tasks]

    return render(request, 'tasks/board.html', {
        'tasks': enhanced_tasks,
        'view_type': 'done' # 完了モード
    })


# --- API (Ajaxステータス更新) ---

@login_required
@require_POST
def api_update_my_status(request):
    """
    Ajax: 自分の進捗ステータスを更新する
    """
    try:
        data = json.loads(request.body)
        task_id = data.get('task_id')
        new_status = data.get('status') # todo, doing, done

        task = get_object_or_404(Task, id=task_id)
        
        # 中間テーブル(TaskAssignment)を更新
        assignment = get_object_or_404(TaskAssignment, task=task, user=request.user)
        assignment.status = new_status
        assignment.save()

        # 全員の進捗を確認
        all_assigns = TaskAssignment.objects.filter(task=task)
        is_task_done = False
        
        # 全員が 'done' ならタスク自体を完了にする
        if all_assigns.count() > 0 and not all_assigns.exclude(status='done').exists():
            task.status = 'done' 
            task.save()
            is_task_done = True
        else:
            # もし完了状態だったのに誰かが戻したなら active に戻す
            if task.status == 'done':
                task.status = 'active'
                task.save()

        # 新しい進捗率を計算して返す
        done_count = all_assigns.filter(status='done').count()
        total = all_assigns.count()
        new_percent = int((done_count / total) * 100) if total > 0 else 0

        return JsonResponse({
            'status': 'success', 
            'progress': new_percent, 
            'task_done': is_task_done
        })

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


# --- 招待リンク ---

@login_required
def join_task_via_link(request, pk):
    task = get_object_or_404(Task, id=pk)
    
    if request.user == task.user or request.user in task.assigned_users.all():
        messages.info(request, "すでにこのタスクに参加しています。")
        return redirect('board')
    
    # 参加処理 (TaskAssignmentを作成)
    TaskAssignment.objects.create(task=task, user=request.user, status='todo')
    
    messages.success(request, f"タスク「{task.title}」に参加しました！")
    return redirect('board')


# --- その他のタスク操作 ---

@login_required
def delete_done_tasks(request):
    if request.method == 'POST':
        # 完了タスクを一括削除
        deleted_count, _ = Task.objects.filter(user=request.user, status='done').delete()
        messages.success(request, f"{deleted_count}件の完了タスクを削除しました。")
    return redirect('done_tasks') # 完了画面へリダイレクト

# --- CBV ---

class TaskCreateView(LoginRequiredMixin, CreateView):
    model = Task
    form_class = TaskForm
    template_name = 'tasks/task_form.html'
    success_url = reverse_lazy('board')

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        
        # 作成者自身をメンバーとして登録
        TaskAssignment.objects.create(task=self.object, user=self.request.user, status='todo')
        return response

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
    # 自分が関わる全タスク
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

# --- 招待機能 (ID指定) ---

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
            elif user_to_invite in task.assigned_users.all():
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
        # 参加処理
        TaskAssignment.objects.create(task=invitation.task, user=request.user, status='todo')
        invitation.save()
        messages.success(request, f"{invitation.task.title} に参加しました！")
    elif response == 'declined':
        invitation.status = 'declined'
        invitation.save()
    return redirect('invitation_list')

@login_required
def leave_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    # TaskAssignmentを削除
    TaskAssignment.objects.filter(task=task, user=request.user).delete()
    messages.success(request, "タスクから退出しました。")
    return redirect('board')

@login_required
def add_comment(request, pk):
    task = get_object_or_404(Task, id=pk)
    if request.method == 'POST':
        content = request.POST.get('content')
        # ★ファイルデータを取得 (request.FILES)
        attachment = request.FILES.get('attachment')
        
        # テキストかファイルのどちらかがあれば保存
        if content or attachment:
            Comment.objects.create(
                task=task, 
                user=request.user, 
                content=content if content else "",
                attachment=attachment
            )
    return redirect('task_edit', pk=pk)

@login_required
def remove_member(request, pk):
    task = get_object_or_404(Task, id=pk)
    if task.user != request.user:
        messages.error(request, "権限がありません。")
        return redirect('task_edit', pk=pk)

    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        if user_id:
            target_user = get_object_or_404(User, id=user_id)
            # TaskAssignmentを削除
            TaskAssignment.objects.filter(task=task, user=target_user).delete()
            # 招待履歴も削除
            Invitation.objects.filter(task=task, recipient=target_user).delete()
            messages.success(request, "メンバーを削除しました。")
    
    return redirect('task_edit', pk=pk)
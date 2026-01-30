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
from .models import Task, TaskAssignment, Invitation, Comment, OneTimePassword, Profile, SubTask
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


# --- ボード表示関連 ---

def enhance_task_data(task, current_user):
    today = timezone.now().date()
    
    # 期限チェック
    if task.due_date:
        delta = (task.due_date.date() - today).days
        task.remaining_days = delta
        if delta < 0:
            task.color_class = 'urgency-red'     # 期限切れ
        elif delta <= 1:
            task.color_class = 'urgency-red'     # 1日以内
        elif delta <= 3:
            task.color_class = 'urgency-yellow'  # 3日以内
        else:
            task.color_class = 'urgency-green'   # 余裕あり
    else:
        task.remaining_days = None
        task.color_class = 'urgency-green'

    # 進捗率計算
    assignments = TaskAssignment.objects.filter(task=task)
    total_members = assignments.count()
    done_members = assignments.filter(status='done').count()
    
    if total_members > 0:
        task.progress_percent = int((done_members / total_members) * 100)
    else:
        task.progress_percent = 0

    # 自分のステータス
    my_assign = assignments.filter(user=current_user).first()
    task.my_status = my_assign.status if my_assign else 'none'
    
    # 表示用メンバーリスト
    task.member_list = assignments

    return task

@login_required
def board(request):
    tasks = Task.objects.filter(
        Q(user=request.user) | Q(assigned_users=request.user)
    ).filter(status='active').distinct().order_by('due_date')

    query = request.GET.get('q')
    if query:
        tasks = tasks.filter(Q(title__icontains=query) | Q(description__icontains=query))

    enhanced_tasks = [enhance_task_data(t, request.user) for t in tasks]

    return render(request, 'tasks/board.html', {
        'tasks': enhanced_tasks,
        'query': query,
        'view_type': 'board'
    })

@login_required
def done_tasks_view(request):
    tasks = Task.objects.filter(
        Q(user=request.user) | Q(assigned_users=request.user)
    ).filter(status='done').distinct().order_by('-updated_at')

    enhanced_tasks = [enhance_task_data(t, request.user) for t in tasks]

    return render(request, 'tasks/board.html', {
        'tasks': enhanced_tasks,
        'view_type': 'done'
    })


# --- API (Ajaxステータス更新) ---

@login_required
@require_POST
def api_update_my_status(request):
    try:
        data = json.loads(request.body)
        task_id = data.get('task_id')
        new_status = data.get('status') # todo, doing, done

        task = get_object_or_404(Task, id=task_id)
        
        # 中間テーブルを更新
        assignment = get_object_or_404(TaskAssignment, task=task, user=request.user)
        assignment.status = new_status
        assignment.save()

        # 全員の進捗を確認してタスク自体の完了判定
        all_assigns = TaskAssignment.objects.filter(task=task)
        is_task_done = False
        
        if all_assigns.count() > 0 and not all_assigns.exclude(status='done').exists():
            task.status = 'done' 
            task.save()
            is_task_done = True
        else:
            if task.status == 'done':
                task.status = 'active'
                task.save()

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


# --- タスク作成・編集 (新詳細画面対応) ---

class TaskCreateView(LoginRequiredMixin, CreateView):
    model = Task
    form_class = TaskForm
    template_name = 'tasks/task_form.html'
    success_url = reverse_lazy('board')

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        TaskAssignment.objects.create(task=self.object, user=self.request.user, status='todo')
        return response

class TaskUpdateView(LoginRequiredMixin, UpdateView):
    model = Task
    form_class = TaskForm
    template_name = 'tasks/task_form.html'
    success_url = reverse_lazy('board')

    def get_queryset(self):
        return Task.objects.filter(Q(user=self.request.user) | Q(assigned_users=self.request.user)).distinct()

    def get_context_data(self, **kwargs):
        # ★ここで「未着手」「進行中」「完了」のメンバーリストを作成してテンプレートに渡します
        context = super().get_context_data(**kwargs)
        task = self.object
        assignments = TaskAssignment.objects.filter(task=task)
        
        context['todo_members'] = assignments.filter(status='todo')
        context['doing_members'] = assignments.filter(status='doing')
        context['done_members'] = assignments.filter(status='done')
        
        return context

class TaskDeleteView(LoginRequiredMixin, DeleteView):
    model = Task
    template_name = 'tasks/task_confirm_delete.html'
    success_url = reverse_lazy('board')
    def get_queryset(self):
        return Task.objects.filter(user=self.request.user)


# --- コメント・ファイル添付 ---

@login_required
def add_comment(request, pk):
    task = get_object_or_404(Task, id=pk)
    if request.method == 'POST':
        content = request.POST.get('content')
        # ★ここを確認
        attachment = request.FILES.get('attachment')
        
        if content or attachment:
            Comment.objects.create(
                task=task, 
                user=request.user, 
                content=content if content else "",
                attachment=attachment
            )
    return redirect('task_edit', pk=pk)


# --- その他機能 ---

@login_required
def delete_done_tasks(request):
    if request.method == 'POST':
        deleted_count, _ = Task.objects.filter(user=request.user, status='done').delete()
        messages.success(request, f"{deleted_count}件の完了タスクを削除しました。")
    return redirect('done_tasks')

@login_required
def join_task_via_link(request, pk):
    task = get_object_or_404(Task, id=pk)
    if request.user == task.user or TaskAssignment.objects.filter(task=task, user=request.user).exists():
        messages.info(request, "すでにこのタスクに参加しています。")
        return redirect('task_edit', pk=task.id)
    
    TaskAssignment.objects.create(task=task, user=request.user, status='todo')
    task.assigned_users.add(request.user) # 念のため
    messages.success(request, f"タスク「{task.title}」に参加しました！")
    return redirect('task_edit', pk=task.id)

@login_required
def invite_user(request, pk):
    task = get_object_or_404(Task, id=pk)
    if request.method == 'POST':
        username = request.POST.get('username')
        try:
            user_to_invite = User.objects.get(username=username)
            if user_to_invite == request.user:
                messages.warning(request, "自分自身は招待できません。")
            elif TaskAssignment.objects.filter(task=task, user=user_to_invite).exists():
                messages.warning(request, "既に参加しています。")
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
        TaskAssignment.objects.create(task=invitation.task, user=request.user, status='todo')
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
    TaskAssignment.objects.filter(task=task, user=request.user).delete()
    task.assigned_users.remove(request.user)
    messages.success(request, "タスクから退出しました。")
    return redirect('board')

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
            TaskAssignment.objects.filter(task=task, user=target_user).delete()
            task.assigned_users.remove(target_user)
            messages.success(request, "メンバーを削除しました。")
    
    return redirect('task_edit', pk=pk)

# プロフィール関連
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

@require_POST
def api_update_role(request):
    data = json.loads(request.body)
    assignment_id = data.get('assignment_id')
    role_name = data.get('role_name')
    
    try:
        assign = TaskAssignment.objects.get(id=assignment_id)
        # オーナーのみ変更可能にするチェック（必要に応じて）
        if request.user != assign.task.user: 
             return JsonResponse({'status': 'error', 'message': '権限がありません'}, status=403)

        assign.role_name = role_name
        assign.save()
        return JsonResponse({'status': 'success'})
    except TaskAssignment.DoesNotExist:
        return JsonResponse({'status': 'error'}, status=404)

# --- WBS（サブタスク）機能 ---
@require_POST
def api_add_subtask(request):
    data = json.loads(request.body)
    task_id = data.get('task_id')
    title = data.get('title')
    
    task = Task.objects.get(id=task_id)
    subtask = SubTask.objects.create(task=task, title=title)
    
    return JsonResponse({
        'status': 'success',
        'subtask_id': subtask.id,
        'title': subtask.title,
        'progress': task.progress_percent()
    })

@require_POST
def api_toggle_subtask(request):
    data = json.loads(request.body)
    subtask_id = data.get('subtask_id')
    
    subtask = SubTask.objects.get(id=subtask_id)
    subtask.is_done = not subtask.is_done
    subtask.save()
    
    return JsonResponse({
        'status': 'success',
        'is_done': subtask.is_done,
        'progress': subtask.task.progress_percent()
    })

@require_POST
def api_delete_subtask(request):
    data = json.loads(request.body)
    subtask_id = data.get('subtask_id')
    subtask = SubTask.objects.get(id=subtask_id)
    task = subtask.task
    subtask.delete()
    return JsonResponse({
        'status': 'success',
        'progress': task.progress_percent()
    })
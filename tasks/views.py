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
import random

# ★ChatThreadを追加
from .models import Task, TaskAssignment, Invitation, Comment, OneTimePassword, Profile, SubTask, ChatThread
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
        
        # コンソールに表示するかメール送信するかはsettings依存
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
        # datetime型同士で計算してからdaysを取得
        delta = (task.due_date - timezone.now()).days
        task.remaining_days = delta
        if delta < 0:
            task.color_class = 'urgency-red'
        elif delta <= 1:
            task.color_class = 'urgency-red'
        elif delta <= 3:
            task.color_class = 'urgency-yellow'
        else:
            task.color_class = 'urgency-green'
    else:
        task.remaining_days = None
        task.color_class = 'urgency-green'

    # WBSに基づく進捗率計算
    task.progress_percent = task.progress_percent()

    # 自分のステータス
    my_assign = TaskAssignment.objects.filter(task=task, user=current_user).first()
    task.my_status = my_assign.status if my_assign else 'none'
    
    # 表示用メンバーリスト
    task.member_list = TaskAssignment.objects.filter(task=task)

    return task

@login_required
def board(request):
    # 自分が関わっているタスク（作成したもの OR アサインされたもの）
    assignments = TaskAssignment.objects.filter(user=request.user)
    task_ids = assignments.values_list('task_id', flat=True)
    
    # status='active' (未完了) のタスクを取得
    tasks = Task.objects.filter(id__in=task_ids).exclude(taskassignment__status='done', taskassignment__user=request.user).distinct().order_by('due_date')

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
    # 完了済みタスク一覧
    assignments = TaskAssignment.objects.filter(user=request.user, status='done')
    task_ids = assignments.values_list('task_id', flat=True)
    
    tasks = Task.objects.filter(id__in=task_ids).distinct().order_by('-created_at')

    enhanced_tasks = [enhance_task_data(t, request.user) for t in tasks]

    return render(request, 'tasks/board.html', {
        'tasks': enhanced_tasks,
        'view_type': 'done'
    })


# --- API (Ajaxステータス更新) ---

@login_required
@require_POST
def api_update_status(request): # URL設定に合わせて関数名を api_update_status に統一
    try:
        data = json.loads(request.body)
        task_id = data.get('task_id')
        new_status = data.get('status') # todo, doing, done

        task = get_object_or_404(Task, id=task_id)
        
        # 中間テーブルを更新
        assignment = get_object_or_404(TaskAssignment, task=task, user=request.user)
        assignment.status = new_status
        assignment.save()

        return JsonResponse({'status': 'success'})

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


# --- タスク作成・編集 ---

class TaskCreateView(LoginRequiredMixin, CreateView):
    model = Task
    form_class = TaskForm
    template_name = 'tasks/task_form.html'
    success_url = reverse_lazy('board')

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        
        # 作成者をリーダーとして追加
        TaskAssignment.objects.create(
            task=self.object, 
            user=self.request.user, 
            status='todo',
            role_name='リーダー'
        )
        
        # ★デフォルトスレッドを作成
        ChatThread.objects.create(task=self.object, name='メイン')
        
        return response

class TaskUpdateView(LoginRequiredMixin, UpdateView):
    model = Task
    form_class = TaskForm
    template_name = 'tasks/task_form.html'

    def get_success_url(self):
        return reverse_lazy('task_edit', kwargs={'pk': self.object.pk})

    def get_queryset(self):
        # 自分が関わっているタスクのみ編集可能
        return Task.objects.filter(taskassignment__user=self.request.user).distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        task = self.object
        
        # ★スレッドがなければ作成（既存データ互換性のため）
        if not task.threads.exists():
            ChatThread.objects.create(task=task, name='メイン')

        assignments = TaskAssignment.objects.filter(task=task)
        context['todo_members'] = assignments.filter(status='todo')
        context['doing_members'] = assignments.filter(status='doing')
        context['done_members'] = assignments.filter(status='done')
        context['is_owner'] = (task.user == self.request.user)
        
        return context

class TaskDeleteView(LoginRequiredMixin, DeleteView):
    model = Task
    template_name = 'tasks/task_confirm_delete.html'
    success_url = reverse_lazy('board')
    def get_queryset(self):
        return Task.objects.filter(user=self.request.user)


# --- コメント・ファイル添付 (スレッド対応版) ---

@login_required
def add_comment(request, pk):
    task = get_object_or_404(Task, id=pk)
    if request.method == 'POST':
        content = request.POST.get('content')
        attachment = request.FILES.get('attachment')
        thread_id = request.POST.get('thread_id')
        msg_type = request.POST.get('message_type', 'normal') # normal または report_done
        
        if content or attachment:
            # スレッド特定
            thread = None
            if thread_id:
                try:
                    thread = ChatThread.objects.get(id=thread_id)
                except ChatThread.DoesNotExist:
                    thread = task.threads.first()
            else:
                thread = task.threads.first()

            Comment.objects.create(
                task=task, 
                user=request.user, 
                content=content if content else "",
                attachment=attachment,
                thread=thread,
                message_type=msg_type
            )
            
            # 完了報告なら自分のステータスを完了にする（オプション）
            if msg_type == 'report_done':
                try:
                    assign = TaskAssignment.objects.get(task=task, user=request.user)
                    assign.status = 'done'
                    assign.save()
                except TaskAssignment.DoesNotExist:
                    pass

    return redirect('task_edit', pk=pk)


# --- その他機能 ---

@login_required
def join_task_via_link(request, pk):
    task = get_object_or_404(Task, id=pk)
    if TaskAssignment.objects.filter(task=task, user=request.user).exists():
        messages.info(request, "すでにこのタスクに参加しています。")
        return redirect('task_edit', pk=task.id)
    
    TaskAssignment.objects.create(task=task, user=request.user, status='todo')
    messages.success(request, f"タスク「{task.title}」に参加しました！")
    return redirect('task_edit', pk=task.id)

@login_required
def remove_member(request, pk):
    task = get_object_or_404(Task, id=pk)
    if task.user != request.user:
        messages.error(request, "権限がありません。")
        return redirect('task_edit', pk=pk)

    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        if user_id:
            TaskAssignment.objects.filter(task=task, user_id=user_id).delete()
            messages.success(request, "メンバーを削除しました。")
    
    return redirect('task_edit', pk=pk)

# プロフィール関連
@login_required
def profile_view(request):
    Profile.objects.get_or_create(user=request.user)
    # 自分が関わっているタスク数
    user_assigns = TaskAssignment.objects.filter(user=request.user)
    context = {
        'tasks_count': user_assigns.count(),
        'done_count': user_assigns.filter(status='done').count(),
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


# --- JSON API群 ---

@require_POST
def api_update_role(request):
    data = json.loads(request.body)
    assignment_id = data.get('assignment_id')
    role_name = data.get('role_name')
    
    try:
        assign = TaskAssignment.objects.get(id=assignment_id)
        if request.user != assign.task.user: 
             return JsonResponse({'status': 'error', 'message': '権限がありません'}, status=403)

        assign.role_name = role_name
        assign.save()
        return JsonResponse({'status': 'success'})
    except TaskAssignment.DoesNotExist:
        return JsonResponse({'status': 'error'}, status=404)

# ★追加: スレッド作成API
@require_POST
def api_create_thread(request):
    data = json.loads(request.body)
    task_id = data.get('task_id')
    name = data.get('name')
    
    task = Task.objects.get(id=task_id)
    thread = ChatThread.objects.create(task=task, name=name)
    
    return JsonResponse({'status': 'success', 'thread_id': thread.id, 'name': thread.name})

# --- WBS API ---
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
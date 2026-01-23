# (import文はそのまま維持してください)
from datetime import timedelta
from dateutil.relativedelta import relativedelta
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.utils import timezone
from django.utils.html import format_html
from django.core.mail import send_mail
from django.conf import settings

from .models import Task, TaskInvitation, Comment, OneTimePassword, Category, Profile
from .forms import TaskForm, CommentForm, SignUpForm, EmailLoginForm, VerificationCodeForm, CategoryForm, UserUpdateForm, ProfileUpdateForm

# --- トップ & プロフィール ---
def index(request):
    if request.user.is_authenticated:
        return redirect('board')
    return redirect('login')

@login_required
def profile_view(request):
    Profile.objects.get_or_create(user=request.user)
    return render(request, 'users/profile.html', {'user': request.user})

@login_required
def profile_edit(request):
    profile, created = Profile.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        u_form = UserUpdateForm(request.POST, instance=request.user)
        p_form = ProfileUpdateForm(request.POST, request.FILES, instance=profile)
        if u_form.is_valid() and p_form.is_valid():
            u_form.save()
            p_form.save()
            messages.success(request, 'プロフィールを更新しました！')
            return redirect('profile')
    else:
        u_form = UserUpdateForm(instance=request.user)
        p_form = ProfileUpdateForm(instance=request.user.profile)
    return render(request, 'users/profile_edit.html', {'u_form': u_form, 'p_form': p_form})

# --- ボード画面 ---
@login_required
def board(request):
    current_user = request.user
    # ▼▼▼ ここを assigned_users に統一 ▼▼▼
    tasks = Task.objects.filter(Q(user=current_user) | Q(assigned_users=current_user)).distinct()

    query = request.GET.get('q')
    selected_category_id = request.GET.get('category')

    if query:
        tasks = tasks.filter(Q(title__icontains=query) | Q(description__icontains=query))
    if selected_category_id:
        tasks = tasks.filter(category_id=selected_category_id)
    
    tasks_todo = tasks.filter(status='todo').order_by('due_date')
    tasks_doing = tasks.filter(status='doing').order_by('due_date')
    tasks_done = tasks.filter(status='done').order_by('due_date')

    categories = Category.objects.filter(user=current_user)
    
    total_tasks = tasks_todo.count() + tasks_doing.count() + tasks_done.count()
    completed_tasks = tasks_done.count()
    progress_percent = int((completed_tasks / total_tasks) * 100) if total_tasks > 0 else 0
        
    context = {
        'tasks_todo': tasks_todo, 'tasks_doing': tasks_doing, 'tasks_done': tasks_done,
        'total_tasks': total_tasks, 'completed_tasks': completed_tasks, 'progress_percent': progress_percent,
        'categories': categories, 'now': timezone.now(),
        'query': query, 'selected_category_id': int(selected_category_id) if selected_category_id else None,
    }
    return render(request, 'tasks/board.html', context)

# --- タスク操作 ---
@login_required
def move_to_doing(request, pk):
    task = get_object_or_404(Task, id=pk)
    # ▼▼▼ assigned_users に統一 ▼▼▼
    if task.user != request.user and request.user not in task.assigned_users.all():
        return redirect('board')
    task.status = 'doing' 
    task.save()
    return redirect('board')

@login_required
def move_to_done(request, pk):
    task = get_object_or_404(Task, id=pk)
    # ▼▼▼ assigned_users に統一 ▼▼▼
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
            user=task.user, title=task.title, description=task.description,
            due_date=next_due_date, status='todo', repeat_mode=task.repeat_mode,
        )
        # ▼▼▼ assigned_users に統一 ▼▼▼
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
        if deleted_count > 0:
            messages.success(request, f"{deleted_count}件の完了タスクを削除しました。")
        else:
            messages.info(request, "完了タスクはありませんでした。")
    return redirect('board')

# --- 招待 & チャット ---
@login_required
def invite_user(request, pk):
    task = get_object_or_404(Task, id=pk)
    # ▼▼▼ assigned_users に統一 ▼▼▼
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
            elif TaskInvitation.objects.filter(task=task, recipient=user_to_invite).exists():
                messages.info(request, "既に招待済みです。")
            else:
                TaskInvitation.objects.create(task=task, sender=request.user, recipient=user_to_invite)
                messages.success(request, f"{username} に招待を送りました。")
        except User.DoesNotExist:
            messages.error(request, f"ユーザー {username} は見つかりません。")
    return redirect('task_edit', pk=task.id)

@login_required
def add_comment(request, pk):
    task = get_object_or_404(Task, id=pk)
    if task.user != request.user and request.user not in task.assigned_users.all():
        return redirect('board')
    if request.method == 'POST':
        text = request.POST.get('text')
        if text:
            Comment.objects.create(task=task, author=request.user, text=text)
    return redirect('task_edit', pk=pk)

@login_required
def invitation_list(request):
    invitations = TaskInvitation.objects.filter(recipient=request.user).order_by('-created_at')
    return render(request, 'tasks/invitation_list.html', {'invitations': invitations})

@login_required
def respond_invitation(request, pk, response):
    invitation = get_object_or_404(TaskInvitation, id=pk)
    if invitation.recipient != request.user:
        return redirect('invitation_list')
    if response == 'accept':
        invitation.task.assigned_users.add(request.user) # ▼▼▼ assigned_users に統一
        messages.success(request, f"タスクに参加しました！")
        invitation.delete()
    elif response == 'decline':
        invitation.delete()
    return redirect('invitation_list')

@login_required
def leave_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    if request.user in task.assigned_users.all(): # ▼▼▼ assigned_users に統一
        task.assigned_users.remove(request.user)
        messages.success(request, "タスクから退出しました。")
    else:
        messages.warning(request, "参加していません。")
    return redirect('board')

# --- CBV (タスク作成など) ---
class CategoryCreateView(LoginRequiredMixin, CreateView):
    model = Category
    form_class = CategoryForm
    template_name = 'tasks/category_form.html'
    success_url = reverse_lazy('task_create')
    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)

class TaskCreateView(LoginRequiredMixin, CreateView):
    model = Task
    form_class = TaskForm
    template_name = 'tasks/task_form.html'
    success_url = reverse_lazy('board')
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)

class TaskUpdateView(LoginRequiredMixin, UpdateView):
    model = Task
    form_class = TaskForm
    template_name = 'tasks/task_form.html'
    success_url = reverse_lazy('board')
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    def get_queryset(self):
        return Task.objects.filter(Q(user=self.request.user) | Q(assigned_users=self.request.user)).distinct()

class TaskDeleteView(LoginRequiredMixin, DeleteView):
    model = Task
    template_name = 'tasks/task_confirm_delete.html'
    success_url = reverse_lazy('board')
    def get_queryset(self):
        return Task.objects.filter(Q(user=self.request.user) | Q(assigned_users=self.request.user)).distinct()

# --- 認証 (そのまま) ---
class SignUpView(CreateView):
    form_class = SignUpForm
    success_url = reverse_lazy('login')
    template_name = 'registration/signup.html'
class CustomLoginView(LoginView):
    authentication_form = EmailLoginForm
    template_name = 'registration/login.html'
    def form_valid(self, form):
        user = form.get_user()
        self.request.session['pre_2fa_user_id'] = user.id
        remember_me = self.request.POST.get('remember_me')
        self.request.session['remember_me'] = True if remember_me else False
        otp, created = OneTimePassword.objects.get_or_create(user=user)
        code = otp.generate_code()
        send_mail("【Kanban】認証コード", f"コード: {code}", settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=True)
        return redirect('verify_code')
def verify_code_view(request):
    user_id = request.session.get('pre_2fa_user_id')
    if not user_id: return redirect('login')
    user = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        form = VerificationCodeForm(request.POST)
        if form.is_valid():
            try:
                otp = OneTimePassword.objects.get(user=user)
                if otp.code == form.cleaned_data.get('code') and otp.is_valid():
                    auth_login(request, user, backend='tasks.backends.EmailBackend')
                    otp.code = ""
                    otp.save()
                    return redirect('board')
            except OneTimePassword.DoesNotExist:
                pass
    else: form = VerificationCodeForm()
    return render(request, 'registration/verify_code.html', {'form': form,'email': user.email})
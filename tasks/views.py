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

# 必要なモデルとフォームを読み込み
# ※ TaskInvitationとCommentを使います
from .models import Task, TaskInvitation, Comment, OneTimePassword, Category, Profile
from .forms import TaskForm, CommentForm, SignUpForm, EmailLoginForm, VerificationCodeForm, CategoryForm, UserUpdateForm, ProfileUpdateForm

# --- 1. トップページ & プロフィール ---

def index(request):
    """トップページ: ログイン済みならボードへ、未ログインならログイン画面へ"""
    if request.user.is_authenticated:
        return redirect('board')
    return redirect('login')

@login_required
def profile_view(request):
    """プロフィール表示"""
    Profile.objects.get_or_create(user=request.user)
    return render(request, 'users/profile.html', {'user': request.user})

@login_required
def profile_edit(request):
    """プロフィール編集 (画像アップロード対応)"""
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

    context = {
        'u_form': u_form,
        'p_form': p_form
    }
    return render(request, 'users/profile_edit.html', context)

# --- 2. カンバンボード (メイン画面) ---

@login_required
def board(request):
    """
    メインのカンバンボード表示
    URL設定の 'board' という名前と一致させるため、関数名を board に統一しました。
    """
    current_user = request.user
    # 自分が作成したタスク または 参加しているタスクを取得
    tasks = Task.objects.filter(Q(user=current_user) | Q(participants=current_user)).distinct()

    # 検索とフィルタリング
    query = request.GET.get('q')
    selected_category_id = request.GET.get('category')

    if query:
        tasks = tasks.filter(Q(title__icontains=query) | Q(description__icontains=query))
    
    if selected_category_id:
        tasks = tasks.filter(category_id=selected_category_id)
    
    # ステータスごとの振り分け
    tasks_todo = tasks.filter(status='todo').order_by('due_date')
    tasks_doing = tasks.filter(status='doing').order_by('due_date')
    tasks_done = tasks.filter(status='done').order_by('due_date')

    categories = Category.objects.filter(user=current_user)
    
    # 進捗計算
    total_tasks = tasks_todo.count() + tasks_doing.count() + tasks_done.count()
    completed_tasks = tasks_done.count()
    progress_percent = int((completed_tasks / total_tasks) * 100) if total_tasks > 0 else 0
        
    context = {
        'tasks_todo': tasks_todo,
        'tasks_doing': tasks_doing,
        'tasks_done': tasks_done,
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'progress_percent': progress_percent,
        'categories': categories,
        'now': timezone.now(),
        'query': query,
        'selected_category_id': int(selected_category_id) if selected_category_id else None,
    }
    return render(request, 'tasks/board.html', context)

# --- 3. タスク操作 (移動・完了・削除) ---

@login_required
def move_to_doing(request, pk): # pkに変更
    task = get_object_or_404(Task, id=pk)
    if task.user != request.user and request.user not in task.participants.all():
        return redirect('board')
    task.status = 'doing' 
    task.save()
    return redirect('board')

@login_required
def move_to_done(request, pk): # pkに変更
    task = get_object_or_404(Task, id=pk)
    if task.user != request.user and request.user not in task.participants.all():
        return redirect('board')
        
    task.status = 'done'
    task.save()
    
    # 繰り返しタスク処理 (既存のロジックを維持)
    if task.repeat_mode != 'none' and task.due_date:
        next_due_date = task.due_date
        if task.repeat_mode == 'daily':
            next_due_date += timedelta(days=1)
        elif task.repeat_mode == 'weekly':
            next_due_date += timedelta(weeks=1)
        elif task.repeat_mode == 'monthly':
            next_due_date += relativedelta(months=1)
        
        new_task = Task.objects.create(
            user=task.user,
            title=task.title,
            description=task.description,
            due_date=next_due_date,
            status='todo',
            repeat_mode=task.repeat_mode,
        )
        for participant in task.participants.all():
            new_task.participants.add(participant)

        messages.success(request, f"タスク完了！次回分（{next_due_date.strftime('%m/%d')}）を自動作成しました。")
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
            messages.info(request, "削除できる完了タスクはありませんでした。")
    return redirect('board')

# --- 4. 招待機能 & チャット機能 ---

@login_required
def invite_user(request, pk):
    """
    ユーザー招待機能
    新しいUIからのリクエストを受け取り、既存のTaskInvitationモデルを使って処理します。
    """
    task = get_object_or_404(Task, id=pk)

    # 権限チェック
    if task.user != request.user and request.user not in task.participants.all():
        messages.error(request, "招待権限がありません。")
        return redirect('board')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        try:
            user_to_invite = User.objects.get(username=username)
            
            # バリデーション
            if user_to_invite == request.user:
                messages.warning(request, "自分自身は招待できません。")
            elif user_to_invite == task.user or user_to_invite in task.participants.all():
                messages.warning(request, f"{username} はすでに参加しています。")
            elif TaskInvitation.objects.filter(task=task, recipient=user_to_invite).exists():
                messages.info(request, f"{username} はすでに招待済みです。")
            else:
                # 既存のTaskInvitationモデルを使用
                TaskInvitation.objects.create(
                    task=task,
                    sender=request.user,
                    recipient=user_to_invite
                )
                
                # メール送信 (既存ロジック維持)
                if user_to_invite.email:
                    subject = f"【Kanban】{request.user.username}さんからタスクへの招待"
                    message = f"""
{user_to_invite.username} 様

{request.user.username} さんが、タスク「{task.title}」にあなたを招待しました。

以下のリンクから確認して承認してください。
{request.scheme}://{request.get_host()}/invitations/
"""
                    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user_to_invite.email], fail_silently=True)

                messages.success(request, f"{username} に招待を送りました。")
        except User.DoesNotExist:
            messages.error(request, f"ユーザー「{username}」は見つかりませんでした。")
            
    # 編集画面に戻る
    return redirect('task_edit', pk=task.id) # urls.pyの名前が task_edit であることを想定

@login_required
def add_comment(request, pk):
    """チャットコメント追加"""
    task = get_object_or_404(Task, id=pk)
    # 参加者チェック
    if task.user != request.user and request.user not in task.participants.all():
        return redirect('board')
    
    if request.method == 'POST':
        text = request.POST.get('text')
        if text:
            Comment.objects.create(
                task=task,
                author=request.user,
                text=text
            )
    return redirect('task_edit', pk=pk)

@login_required
def invitation_list(request):
    invitations = TaskInvitation.objects.filter(recipient=request.user).order_by('-created_at')
    return render(request, 'tasks/invitation_list.html', {'invitations': invitations })

@login_required
def respond_invitation(request, pk, response): # pkとresponseに変更
    # invite_id -> pk, action -> response に合わせて既存ロジックをラップ
    invitation = get_object_or_404(TaskInvitation, id=pk)

    if invitation.recipient != request.user:
        return redirect('invitation_list')
    
    if response == 'accept':
        invitation.task.participants.add(request.user)
        messages.success(request, f"タスク「{invitation.task.title}」に参加しました！")
        invitation.delete()
    elif response == 'decline':
        messages.info(request, f"タスク「{invitation.task.title}」への招待を辞退しました。")
        invitation.delete()

    return redirect('invitation_list')

@login_required
def leave_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    if request.user in task.participants.all():
        task.participants.remove(request.user)
        messages.success(request, f"タスク「{task.title}」から退出しました。")
    else:
        messages.warning(request, "そのタスクには参加していません。")
    return redirect('board')

# --- 5. クラスベースビュー (CRUD) ---

class CategoryCreateView(LoginRequiredMixin, CreateView):
    model = Category
    form_class = CategoryForm
    template_name = 'tasks/category_form.html'
    success_url = reverse_lazy('task_create')

    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, f"カテゴリ「{form.instance.name}」を作成しました")
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
        response = super().form_valid(form)
        
        # GCal連携
        if form.cleaned_data.get('add_to_gcal'):
            link = self.object.get_gcal_link()
            if link:
                msg = format_html(
                    'タスク作成。<a href="{}" target="_blank" class="fw-bold text-decoration-underline">Googleカレンダーに追加</a>',
                    link
                )
                messages.success(self.request, msg)
            else:
                messages.success(self.request, "タスクを作成しました。")
        else:
            messages.success(self.request, "タスクを作成しました。")
        return response

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
        return Task.objects.filter(Q(user=self.request.user) | Q(participants=self.request.user)).distinct()
    
    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "タスクを更新しました。")
        return response

class TaskDeleteView(LoginRequiredMixin, DeleteView):
    model = Task
    template_name = 'tasks/task_confirm_delete.html'
    success_url = reverse_lazy('board')

    def get_queryset(self):
        return Task.objects.filter(Q(user=self.request.user) | Q(participants=self.request.user)).distinct()

# --- 6. 認証関連 (2段階認証など) ---

class SignUpView(CreateView):
    form_class = SignUpForm
    success_url = reverse_lazy('login')
    template_name = 'registration/signup.html'

class CustomLoginView(LoginView):
    authentication_form = EmailLoginForm
    template_name = 'login.html' # registration/login.html かもしれませんが一旦維持

    def form_valid(self, form):
        user = form.get_user()
        self.request.session['pre_2fa_user_id'] = user.id
        remember_me = self.request.POST.get('remember_me')
        self.request.session['remember_me'] = True if remember_me else False
        otp, created = OneTimePassword.objects.get_or_create(user=user)
        code = otp.generate_code()
        
        # メール送信
        subject = "【Kanban】ログイン認証コード"
        message = f"コード: {code}\n※このコードは10分間有効です。"
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=True)
        return redirect('verify_code')
    
def verify_code_view(request):
    user_id = request.session.get('pre_2fa_user_id')
    if not user_id:
        return redirect('login')
    user = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        form = VerificationCodeForm(request.POST)
        if form.is_valid():
            input_code = form.cleaned_data.get('code')
            try:
                otp = OneTimePassword.objects.get(user=user)
                if otp.code == input_code and otp.is_valid():
                    # セッション有効期限設定
                    if request.session.get('remember_me'):
                        request.session.set_expiry(1209600)
                    else:
                        request.session.set_expiry(0)
                    
                    auth_login(request, user, backend='tasks.backends.EmailBackend')
                    
                    # セッション掃除
                    if 'pre_2fa_user_id' in request.session: del request.session['pre_2fa_user_id']
                    if 'remember_me' in request.session: del request.session['remember_me']

                    otp.code = ""
                    otp.save()

                    messages.success(request, "ログインしました!")
                    return redirect('board')
                else:
                    messages.error(request, "コードが間違っているか、有効期限が切れています。")
            except OneTimePassword.DoesNotExist:
                messages.error(request, "認証コードが見つかりません。")
    else:
        form = VerificationCodeForm()
    
    return render(request, 'registration/verify_code.html', {'form': form,'email': user.email})
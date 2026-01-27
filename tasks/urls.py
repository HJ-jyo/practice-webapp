from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    # --- 認証系 ---
    path('signup/', views.SignUpView.as_view(), name='signup'),
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('verify_code/', views.verify_code_view, name='verify_code'),
    
    # パスワードリセット
    path('password_reset/', auth_views.PasswordResetView.as_view(), name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(), name='password_reset_complete'),

    # --- メイン機能 ---
    path('', views.index, name='index'),
    path('board/', views.board, name='board'),
    # 完了タスク専用画面
    path('board/done/', views.done_tasks_view, name='done_tasks'),

    # --- タスク操作 ---
    path('task/create/', views.TaskCreateView.as_view(), name='task_create'),
    path('task/<int:pk>/edit/', views.TaskUpdateView.as_view(), name='task_edit'),
    path('task/<int:pk>/delete/', views.TaskDeleteView.as_view(), name='task_delete'),
    
    # Ajax更新用API
    path('api/update_status/', views.api_update_my_status, name='api_update_status'),

    # ★修正: 古い移動用URL（move_to_doing, move_to_done）を削除しました
    # 完了タスクの一括削除機能は views.py に存在するため残します
    path('delete_done_tasks/', views.delete_done_tasks, name='delete_done_tasks'),

    # --- コミュニケーション & 招待 ---
    path('task/<int:pk>/comment/', views.add_comment, name='add_comment'),
    path('task/<int:pk>/invite/', views.invite_user, name='invite_user'),
    path('invitations/', views.invitation_list, name='invitation_list'),
    path('invitation/<int:pk>/<str:response>/', views.respond_invitation, name='respond_invitation'),
    
    # 招待リンク用URL
    path('task/<int:pk>/join/', views.join_task_via_link, name='join_task_via_link'),

    path('task/<int:pk>/leave/', views.leave_task, name='leave_task'),
    path('task/<int:pk>/remove_member/', views.remove_member, name='remove_member'),

    # --- プロフィール ---
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.profile_edit, name='profile_edit'),
]

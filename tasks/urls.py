from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    # --- 認証系 ---
    path('signup/', views.SignUpView.as_view(), name='signup'),
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('verify_code/', views.verify_code_view, name='verify_code'),
    
    # パスワードリセット（Django標準機能を使う場合）
    path('password_reset/', auth_views.PasswordResetView.as_view(), name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(), name='password_reset_complete'),

    # --- メイン機能 ---
    path('', views.index, name='index'),
    path('board/', views.board, name='board'),

    # --- タスク操作 (既存 & Ajax) ---
    path('task/create/', views.TaskCreateView.as_view(), name='task_create'),
    path('task/<int:pk>/edit/', views.TaskUpdateView.as_view(), name='task_edit'),
    path('task/<int:pk>/delete/', views.TaskDeleteView.as_view(), name='task_delete'),
    
    # Ajax用API
    path('api/move_task/', views.api_move_task, name='api_move_task'),

    # 既存の移動ボタン用 (フォールバック)
    path('task/<int:pk>/move_doing/', views.move_to_doing, name='move_to_doing'),
    path('task/<int:pk>/move_done/', views.move_to_done, name='move_to_done'),
    path('delete_done_tasks/', views.delete_done_tasks, name='delete_done_tasks'),

    # --- コミュニケーション & 招待 ---
    path('task/<int:pk>/comment/', views.add_comment, name='add_comment'),
    path('task/<int:pk>/invite/', views.invite_user, name='invite_user'),
    path('invitations/', views.invitation_list, name='invitation_list'),
    path('invitation/<int:pk>/<str:response>/', views.respond_invitation, name='respond_invitation'),
    
    # ★招待リンク用URL (これを踏むと参加できる)
    path('task/<int:pk>/join/', views.join_task_via_link, name='join_task_via_link'),

    path('task/<int:pk>/leave/', views.leave_task, name='leave_task'),
    path('task/<int:pk>/remove_member/', views.remove_member, name='remove_member'),

    # --- プロフィール ---
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.profile_edit, name='profile_edit'),
]
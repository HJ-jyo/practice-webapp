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
    path('board/done/', views.done_tasks_view, name='done_tasks'),

    # --- タスク操作 ---
    path('task/create/', views.TaskCreateView.as_view(), name='task_create'),
    path('task/<int:pk>/edit/', views.TaskUpdateView.as_view(), name='task_edit'),
    path('task/<int:pk>/delete/', views.TaskDeleteView.as_view(), name='task_delete'),
    
    # API
    path('api/update_status/', views.api_update_status, name='api_update_status'),

    # --- コミュニケーション ---
    path('task/<int:pk>/comment/', views.add_comment, name='add_comment'),
    path('task/<int:pk>/join/', views.join_task_via_link, name='join_task_via_link'),
    path('task/<int:pk>/remove_member/', views.remove_member, name='remove_member'),

    # --- プロフィール ---
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.profile_edit, name='profile_edit'),

    # --- WBS & チャットスレッド機能 ---
    path('api/update_role/', views.api_update_role, name='api_update_role'),
    path('api/add_subtask/', views.api_add_subtask, name='api_add_subtask'),
    path('api/toggle_subtask/', views.api_toggle_subtask, name='api_toggle_subtask'),
    path('api/delete_subtask/', views.api_delete_subtask, name='api_delete_subtask'),
    path('api/create_thread/', views.api_create_thread, name='api_create_thread'),
]
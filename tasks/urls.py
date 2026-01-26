from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # トップ & 認証
    path('', views.index, name='index'),
    path('signup/', views.SignUpView.as_view(), name='signup'),
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('verify_code/', views.verify_code_view, name='verify_code'),

    path('password_reset/', auth_views.PasswordResetView.as_view(template_name='registration/password_reset_form.html'), name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='registration/password_reset_done.html'), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='registration/password_reset_confirm.html'), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(template_name='registration/password_reset_complete.html'), name='password_reset_complete'),

    # プロフィール
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.profile_edit, name='profile_edit'),

    # メインボード
    path('board/', views.board, name='board'),

    # タスク操作
    path('task/create/', views.TaskCreateView.as_view(), name='task_create'),
    path('edit/<int:pk>/', views.TaskUpdateView.as_view(), name='task_edit'),
    path('task/<int:pk>/delete/', views.TaskDeleteView.as_view(), name='task_delete'),
    
    # ステータス移動
    path('task/<int:pk>/move_doing/', views.move_to_doing, name='move_to_doing'),
    path('task/<int:pk>/move_done/', views.move_to_done, name='move_to_done'),
    path('tasks/delete_done/', views.delete_done_tasks, name='delete_done_tasks'),

    # 招待・チャット機能
    path('task/<int:pk>/invite/', views.invite_user, name='invite_user'),
    path('task/<int:pk>/remove_member/', views.remove_member, name='remove_member'), 
    path('task/<int:pk>/comment/', views.add_comment, name='add_comment'),
    
    # 招待リスト & 応答
    path('invitations/', views.invitation_list, name='invitation_list'),
    path('invitations/<int:pk>/<str:response>/', views.respond_invitation, name='respond_invitation'),
    path('task/<int:task_id>/leave/', views.leave_task, name='leave_task'),
]
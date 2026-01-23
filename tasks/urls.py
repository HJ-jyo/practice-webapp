from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('board/', views.board, name='board'),
    
    # タスク管理
    path('task/create/', views.task_create, name='task_create'),
    path('edit/<int:pk>/', views.task_edit, name='task_edit'), # ←ここが task_edit になっているか確認
    path('task/<int:pk>/delete/', views.task_delete, name='task_delete'),
    
    # ステータス移動
    path('task/<int:pk>/move_todo/', views.move_to_todo, name='move_to_todo'),
    path('task/<int:pk>/move_doing/', views.move_to_doing, name='move_to_doing'),
    path('task/<int:pk>/move_done/', views.move_to_done, name='move_to_done'),
    path('tasks/delete_done/', views.delete_done_tasks, name='delete_done_tasks'),

    # カテゴリ
    path('category/create/', views.category_create, name='category_create'),

    # ユーザー・プロフィール
    path('signup/', views.signup, name='signup'),
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.profile_edit, name='profile_edit'),
    
    # ▼▼▼ 今回復活させる機能 (招待・チャット) ▼▼▼
    path('task/<int:pk>/invite/', views.invite_user, name='invite_user'),     # 招待機能
    path('task/<int:pk>/comment/', views.add_comment, name='add_comment'),    # チャット機能
    path('invitations/', views.invitation_list, name='invitation_list'),      # 招待リスト
    path('invitations/<int:pk>/<str:response>/', views.respond_invitation, name='respond_invitation'), # 参加/辞退
]
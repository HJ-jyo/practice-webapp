from django.urls import path
from . import views

urlpatterns = [
    path('', views.board_view, name='board'),
    path('signup/', views.SignUpView.as_view(), name='signup'),
    path('create/', views.TaskCreateView.as_view(), name='task_create'),
    path('edit/<int:pk>/', views.TaskUpdateView.as_view(), name='task_edit'),
    path('delete/<int:pk>/', views.TaskDeleteView.as_view(), name='task_delete'),
    path('move_to_doing/<int:task_id>/', views.move_to_doing, name='move_to_doing'),
    path('move_to_done/<int:task_id>/', views.move_to_done, name='move_to_done'),
    path('delete_done/', views.delete_done_tasks, name='delete_done_tasks'),
    path('join/<uuid:token>/', views.join_task_confirm, name='task_join'),
    path('task/<int:task_id>/add_member/', views.add_member_by_username, name='add_member'),
    path('invitations/', views.invitation_list, name='invitation_list'),
    path('invitations/<int:invite_id>/<str:action>/', views.respond_invitation, name='respond_invitation'),
    path('task/<int:task_id>/add_comment/', views.add_comment, name='add_comment'),
    path('task/<int:task_id>/leave/', views.leave_task, name='leave_task'),
    path('verify-code/', views.verify_code_view, name='verify_code'),
    path('category/create/', views.CategoryCreateView.as_view(), name='category_create'),
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.profile_edit_view, name='profile_edit'),
]
from django.urls import path
from . import views

urlpatterns = [
    # Auth endpoints
    path('auth/login/', views.LoginView.as_view()),
    path('auth/send-otp/', views.SendOTPView.as_view()),
    path('auth/verify-otp/', views.VerifyOTPView.as_view()),
    path('auth/forgot-password/', views.ForgotPasswordView.as_view()),
    path('auth/reset-password/', views.ResetPasswordView.as_view()),

    # User endpoints (APIView)
    path('users/', views.UserListCreateView.as_view()),
    path('users/<int:pk>/', views.UserDetailView.as_view()),
    path('users/<int:pk>/activate/', views.UserActivateView.as_view()),
    path('users/<int:pk>/deactivate/', views.UserDeactivateView.as_view()),

    # Profile endpoints
    path('profiles/', views.ProfileListCreateView.as_view()),
    path('profiles/<int:pk>/', views.ProfileDetailView.as_view()),

    # Client endpoints (APIView)
    path('clients/', views.ClientListCreateView.as_view()),
    path('clients/<int:pk>/', views.ClientDetailView.as_view()),
    path('clients/<int:pk>/activate/', views.ClientActivateView.as_view()),
    path('clients/<int:pk>/deactivate/', views.ClientDeactivateView.as_view()),

    # Project endpoints (APIView)
    path('projects/', views.ProjectListCreateView.as_view()),            
    path('projects/<int:pk>/', views.ProjectDetailView.as_view()),

    path('users/<int:pk>/restore/', views.UserRestoreView.as_view()),
    path('clients/<int:pk>/restore/', views.ClientRestoreView.as_view()),
    path('projects/<int:pk>/restore/', views.ProjectRestoreView.as_view()),

    # Task endpoints
    path('tasks/', views.TaskListView.as_view()),
    path('projects/<int:project_id>/tasks/', views.ProjectTaskListCreateView.as_view()),
    path('tasks/<int:pk>/', views.ProjectTaskDetailView.as_view()),
    path('tasks/<int:task_id>/comments/', views.TaskCommentListCreateView.as_view()),
    path('comments/<int:pk>/', views.TaskCommentDetailView.as_view()),
    path('tasks/<int:pk>/activate/', views.ProjectTaskActivateView.as_view()),
     
]

from django.urls import path
from . import views
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    # Auth endpoints
    path('auth/login/', views.LoginView.as_view()),
    path('auth/me/', views.MeView.as_view()),
    path('health/', views.HealthView.as_view()),
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

    # Lookup endpoints (project type, project status, task status)
    path('lookups/', views.LookupListCreateView.as_view()),
    path('lookups/<int:pk>/', views.LookupDetailView.as_view()),

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

    # Auth endpoints ke saath
    path('auth/refresh/', TokenRefreshView.as_view()),
    path('projects/team-overview/', views.ProjectTeamOverviewView.as_view()),
    path('projects/<int:pk>/team/', views.ProjectTeamView.as_view()),
    path('projects/<int:pk>/team-leaders/', views.ProjectTeamLeaderView.as_view()),
    path('projects/<int:pk>/team-leaders/<int:user_id>/', views.ProjectTeamLeaderView.as_view()),
    path('me/work/', views.MyWorkView.as_view()),
    path('users/<int:pk>/work/', views.UserWorkView.as_view()),
    path('auth/logout/', views.LogoutView.as_view()),
    path('projects/<int:pk>/activity/', views.ProjectActivityView.as_view()),
    path('tasks/<int:pk>/activity/', views.TaskActivityView.as_view()),
    path('tasks/<int:task_id>/attachments/', views.TaskAttachmentListCreateView.as_view()),
    path('attachments/<int:pk>/', views.TaskAttachmentDetailView.as_view()),
    path('dashboard/', views.DashboardView.as_view()),
]

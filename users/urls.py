from django.urls import path
from . import views

urlpatterns = [
    # User endpoints (APIView)
    path('users/', views.UserListCreateView.as_view()),
    path('users/<int:pk>/', views.UserDetailView.as_view()),
    path('users/<int:pk>/activate/', views.UserActivateView.as_view()),
    path('users/<int:pk>/deactivate/', views.UserDeactivateView.as_view()),

    # Client endpoints (APIView)
    path('clients/', views.ClientListCreateView.as_view()),
    path('clients/<int:pk>/', views.ClientDetailView.as_view()),
    path('clients/<int:pk>/activate/', views.ClientActivateView.as_view()),
    path('clients/<int:pk>/deactivate/', views.ClientDeactivateView.as_view()),

    # Auth endpoints
    path('auth/login/', views.LoginView.as_view()),
    path('auth/send-otp/', views.SendOTPView.as_view()),
    path('auth/verify-otp/', views.VerifyOTPView.as_view()),
    path('auth/forgot-password/', views.ForgotPasswordView.as_view()),
    path('auth/reset-password/', views.ResetPasswordView.as_view()),
]
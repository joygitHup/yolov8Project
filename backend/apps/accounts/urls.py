from django.urls import path
from . import views

urlpatterns = [
    path("login", views.LoginView.as_view()),
    path("logout", views.LogoutView.as_view()),
    path("me", views.MeView.as_view()),
    path("change-password", views.ChangePasswordView.as_view()),
    path("users", views.UserListCreateView.as_view()),
    path("users/<int:pk>/reset-password", views.ResetPasswordView.as_view()),
    path("users/<int:pk>/toggle-status", views.UserToggleStatusView.as_view()),
    path("users/<int:pk>", views.UserDetailView.as_view()),
]

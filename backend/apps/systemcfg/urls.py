from django.urls import path
from . import views

urlpatterns = [
    path("public", views.PublicSettingsView.as_view()),
    path("settings", views.SettingsView.as_view()),
    path("detection", views.DetectionView.as_view()),
    path("notification/test", views.NotificationTestView.as_view()),
    path("notification/logs", views.NotificationLogView.as_view()),
    path("notification", views.NotificationView.as_view()),
    path("strategies/<int:pk>/toggle", views.StrategyToggleView.as_view()),
    path("strategies/<int:pk>", views.StrategyDetailView.as_view()),
    path("strategies", views.StrategyListCreateView.as_view()),
    path("system/info", views.SystemInfoView.as_view()),
]

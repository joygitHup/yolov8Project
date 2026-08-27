from django.urls import path
from . import views

urlpatterns = [
    path("overview", views.OverviewView.as_view()),
    path("alert-trend", views.AlertTrendView.as_view()),
    path("alert-types", views.AlertTypesView.as_view()),
    path("alert-levels", views.AlertLevelsView.as_view()),
    path("camera-rank", views.CameraRankView.as_view()),
    path("recent-alerts", views.RecentAlertsView.as_view()),
    path("area-distribution", views.AreaDistributionView.as_view()),
    path("realtime-detections", views.RealtimeDetectionsView.as_view()),
]

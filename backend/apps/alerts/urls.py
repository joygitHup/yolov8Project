from django.urls import path
from . import views

urlpatterns = [
    path("stats", views.AlertStatsView.as_view()),
    path("heatmap/data", views.AlertHeatmapView.as_view()),
    path("batch-handle", views.AlertBatchHandleView.as_view()),
    path("<int:pk>/handle", views.AlertHandleView.as_view()),
    path("<int:pk>/evidence", views.AlertEvidenceView.as_view()),
    path("<int:pk>/report", views.AlertReportView.as_view()),
    path("<int:pk>/dispatch", views.AlertDispatchView.as_view()),
    path("<int:pk>", views.AlertDetailView.as_view()),
    path("", views.AlertListView.as_view()),
]

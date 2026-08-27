from django.urls import path
from . import views

urlpatterns = [
    path("all", views.CameraAllView.as_view()),
    path("monitor", views.CameraMonitorWallView.as_view()),
    path("batch-delete", views.CameraBatchDeleteView.as_view()),
    path("<int:pk>/detection", views.CameraDetectionView.as_view()),
    path("<int:pk>/toggle", views.CameraToggleView.as_view()),
    path("<int:pk>/ptz", views.CameraPtzView.as_view()),
    path("<int:pk>/snapshot", views.CameraSnapshotView.as_view()),
    path("<int:pk>/record", views.CameraRecordView.as_view()),
    path("<int:pk>", views.CameraDetailView.as_view()),
    path("", views.CameraListCreateView.as_view()),
]

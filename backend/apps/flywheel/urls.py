from django.urls import path
from . import views

urlpatterns = [
    path("flywheel/stats", views.FlywheelStatsView.as_view()),
    path("flywheel/train/<int:pk>/promote", views.FlywheelTrainPromoteView.as_view()),
    path("flywheel/train/<int:pk>/rollback", views.FlywheelTrainRollbackView.as_view()),
    path("flywheel/train", views.FlywheelTrainView.as_view()),
    path("flywheel/samples/next", views.FlywheelSampleNextView.as_view()),
    path("flywheel/samples/<int:pk>/image", views.FlywheelSampleImageView.as_view()),
    path("flywheel/samples/<int:pk>/approve", views.FlywheelSampleApproveView.as_view()),
    path("flywheel/samples/<int:pk>/discard", views.FlywheelSampleDiscardView.as_view()),
    path("flywheel/samples/<int:pk>", views.FlywheelSampleDetailView.as_view()),
    path("flywheel/samples", views.FlywheelSampleListView.as_view()),
    path("flywheel", views.FlywheelConfigView.as_view()),
]

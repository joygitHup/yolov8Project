from django.urls import path
from . import views

urlpatterns = [
    path("<int:pk>/stream/start", views.CameraStreamStartView.as_view()),
    path("<int:pk>/stream/stop", views.CameraStreamStopView.as_view()),
    path("<int:pk>/stream", views.CameraStreamView.as_view()),
]

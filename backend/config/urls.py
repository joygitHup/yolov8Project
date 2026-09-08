from django.urls import include, path
from apps.common.views import HealthView
from apps.cameras.views import CameraListCreateView
from apps.alerts.views import AlertListView
from apps.streaming.views import AlertMediaView, HlsMediaView

urlpatterns = [
    path("api/health", HealthView.as_view()),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/cameras", CameraListCreateView.as_view()),
    path("api/cameras/", include("apps.streaming.urls")),
    path("api/cameras/", include("apps.cameras.urls")),
    path("api/alerts", AlertListView.as_view()),
    path("api/alerts/", include("apps.alerts.urls")),
    path("api/config/", include("apps.systemcfg.urls")),
    path("api/config/", include("apps.flywheel.urls")),
    path("api/dashboard/", include("apps.dashboard.urls")),
    path("api/inference/", include("apps.inference.urls")),
    path("media/hls/<int:camera_id>/<str:filename>", HlsMediaView.as_view()),
    path("media/alerts/<int:alert_id>/<str:filename>", AlertMediaView.as_view()),
]

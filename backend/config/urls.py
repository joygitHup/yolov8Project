from django.urls import include, path
from apps.common.views import HealthView
from apps.cameras.views import CameraListCreateView
from apps.alerts.views import AlertListView

urlpatterns = [
    path("api/health", HealthView.as_view()),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/cameras", CameraListCreateView.as_view()),
    path("api/cameras/", include("apps.cameras.urls")),
    path("api/alerts", AlertListView.as_view()),
    path("api/alerts/", include("apps.alerts.urls")),
    path("api/config/", include("apps.systemcfg.urls")),
    path("api/dashboard/", include("apps.dashboard.urls")),
]

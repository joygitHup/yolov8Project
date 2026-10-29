from django.http import HttpResponse
from django.urls import include, path
from apps.common.views import HealthView
from apps.cameras.views import CameraListCreateView
from apps.alerts.views import AlertListView
from apps.streaming.views import AlertMediaView, HlsMediaView, MtxHlsProxyView


def _metrics_prometheus(request):
    """
    Minimal Prometheus-style /metrics endpoint. No external dep — just
    our in-memory counters + gauges + live DB totals.
    """
    from apps.common.middleware import snapshot_metrics

    lines = []
    # 1. Built-in HTTP metrics from TraceIDMiddleware
    snap = snapshot_metrics()
    for name, value in sorted(snap.items()):
        lines.append(f"{name} {value}")

    # 2. Live DB counters
    try:
        from apps.alerts.models import Alert

        lines.append(f"alerts_total {Alert.objects.count()}")
        lines.append(f"alerts_unhandled {Alert.objects.filter(status='unhandled').count()}")
    except Exception:
        pass

    try:
        from apps.cameras.models import Camera

        lines.append(f"cameras_total {Camera.objects.count()}")
        lines.append(f"cameras_enabled {Camera.objects.filter(enabled=True).count()}")
    except Exception:
        pass

    body = "\n".join(lines) + "\n"
    return HttpResponse(body, content_type="text/plain; version=0.0.4; charset=utf-8")


urlpatterns = [
    path("api/health", HealthView.as_view()),
    path("metrics", _metrics_prometheus),
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
    path("media/mtx/<str:mtx_path>/<str:filename>", MtxHlsProxyView.as_view()),
    path("media/alerts/<int:alert_id>/<str:filename>", AlertMediaView.as_view()),
]

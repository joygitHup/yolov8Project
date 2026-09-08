import time

from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from django.conf import settings as dj_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.alerts.models import Alert
from apps.cameras.models import Camera
from apps.common.permissions import IsAdminOrOperator, IsAdminRole
from apps.common.sysmetrics import collect_system_metrics
from apps.inference.notify import CHANNEL_LABEL, send_channel
from apps.realtime.broadcast import broadcast
from .models import NotificationLog, Strategy
from .serializers import StrategySerializer
from .services import (
    apply_settings_patch,
    deep_merge,
    get_all_settings,
    get_section,
    normalize_settings,
    save_section,
)


def _uptime_text():
    started = getattr(dj_settings, "STARTED_AT", None) or time.time()
    delta_sec = time.time() - float(started)
    days, rem = divmod(int(delta_sec), 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    return f"{days}天 {hours}小时 {minutes}分"


def _publish(section, payload=None):
    data = {"section": section, "settings": get_all_settings()}
    if payload:
        data.update(payload)
    broadcast("config:updated", data)
    return data


def _clamp(value, low, high, default):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


class PublicSettingsView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        system = get_section("system")
        return Response({
            "title": system["title"],
            "logo": system["logo"],
            "version": system["version"],
        })


class SettingsView(APIView):
    def get_permissions(self):
        if self.request.method == "PUT":
            return [IsAuthenticated(), IsAdminRole()]
        return [IsAuthenticated()]

    def get(self, request):
        return Response(get_all_settings())

    def put(self, request):
        try:
            settings = apply_settings_patch(dict(request.data))
        except ValueError as exc:
            raise ValidationError(str(exc))
        _publish("settings")
        return Response({
            "message": "设置已更新并生效",
            "settings": settings,
        })


class DetectionView(APIView):
    def get_permissions(self):
        if self.request.method == "PUT":
            return [IsAuthenticated(), IsAdminOrOperator()]
        return [IsAuthenticated()]

    def get(self, request):
        return Response(get_section("detection"))

    def put(self, request):
        import logging

        from apps.systemcfg.services import normalize_detection

        patch = dict(request.data)
        before = get_section("detection")
        detection = normalize_detection(deep_merge(before, patch))
        save_section("detection", detection)
        _publish("detection", {"detection": detection})

        new_path = (detection.get("modelPath") or "").strip()
        old_path = (before.get("modelPath") or "").strip()
        if new_path and new_path != old_path:
            try:
                from apps.inference import remote as yolo_remote

                if yolo_remote.infer_mode() == "remote":
                    yolo_remote.reload_model(new_path)
            except Exception as exc:
                logging.getLogger("systemcfg").warning(
                    "remote model reload on save failed: %s", exc
                )
        try:
            from apps.flywheel.jobs import job_write_yaml

            job_write_yaml({})
        except Exception:
            pass

        return Response({"message": "检测参数已更新并立即生效", "detection": detection})


class NotificationView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        return Response(get_section("notification"))

    def put(self, request):
        notification = deep_merge(get_section("notification"), dict(request.data))
        save_section("notification", notification)
        _publish("notification", {"notification": notification})
        return Response({"message": "通知配置已更新并立即生效", "notification": notification})


class NotificationTestView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def post(self, request):
        channel = request.data.get("channel")
        if channel not in CHANNEL_LABEL:
            raise ValidationError("不支持的通知渠道")
        text = request.data.get("text") or f"【测试】{CHANNEL_LABEL[channel]} 通道连通性测试"
        result = send_channel(channel, text, kind="test")
        return Response(result)


class NotificationLogView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        qs = NotificationLog.objects.all()[:50]
        return Response({
            "list": [
                {
                    "id": row.id,
                    "channel": row.channel,
                    "kind": row.kind,
                    "success": row.success,
                    "message": row.message,
                    "alertId": row.alert_id,
                    "createdAt": row.created_at.isoformat() if row.created_at else None,
                }
                for row in qs
            ],
            "total": NotificationLog.objects.count(),
        })


class StrategyListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), IsAdminOrOperator()]
        return [IsAuthenticated()]

    def get(self, request):
        items = StrategySerializer(Strategy.objects.all(), many=True).data
        return Response({"list": items, "total": len(items)})

    def post(self, request):
        if not request.data.get("name") or not request.data.get("cameraIds") or not request.data.get("detectionTypes"):
            raise ValidationError("请填写完整的策略信息")
        ser = StrategySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        strategy = ser.save()
        _publish("strategies")
        return Response(StrategySerializer(strategy).data)


class StrategyDetailView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [IsAuthenticated()]
        return [IsAuthenticated(), IsAdminOrOperator()]

    def _get(self, pk):
        obj = Strategy.objects.filter(pk=pk).first()
        if not obj:
            raise NotFound("策略不存在")
        return obj

    def get(self, request, pk):
        return Response(StrategySerializer(self._get(pk)).data)

    def put(self, request, pk):
        obj = self._get(pk)
        ser = StrategySerializer(obj, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        _publish("strategies")
        return Response(StrategySerializer(obj).data)

    def delete(self, request, pk):
        self._get(pk).delete()
        _publish("strategies")
        return Response({"message": "删除成功"})


class StrategyToggleView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrOperator]

    def post(self, request, pk):
        obj = Strategy.objects.filter(pk=pk).first()
        if not obj:
            raise NotFound("策略不存在")
        if "enabled" in request.data:
            obj.enabled = bool(request.data.get("enabled"))
        else:
            obj.enabled = not obj.enabled
        obj.save(update_fields=["enabled"])
        _publish("strategies")
        return Response({"enabled": obj.enabled})


class SystemInfoView(APIView):
    """
    Canonical system info for the settings page:
      system: { title, version, environment, uptime, cpuPercent, memoryPercent, gpuPercent }
      stats:  { cameras{total,online,offline,enabled}, alerts{total,today,unhandled},
                users{total,active}, strategies{total,enabled} }
      detection / alertDeduplication — current related sections
    """

    def get(self, request):
        cameras = Camera.objects.all()
        today = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
        system = get_section("system")
        detection = get_section("detection")
        dedup = get_section("alertDeduplication")
        metrics = collect_system_metrics()
        uptime = _uptime_text()
        cpu = metrics.get("cpu")
        memory = metrics.get("memory")
        gpu = metrics.get("gpu")
        return Response({
            "system": {
                "title": system["title"],
                "logo": system["logo"],
                "version": system["version"],
                "environment": "development" if dj_settings.DEBUG else "production",
                "uptime": uptime,
                "cpuPercent": cpu,
                "memoryPercent": memory,
                "gpuPercent": gpu,
                # aliases kept for older UI bindings
                "name": system["title"],
                "cpu": cpu,
                "memory": memory,
                "gpu": gpu,
            },
            "stats": {
                "cameras": {
                    "total": cameras.count(),
                    "online": cameras.filter(status="online").count(),
                    "offline": cameras.filter(status="offline").count(),
                    "enabled": cameras.filter(enabled=True).count(),
                },
                "alerts": {
                    "total": Alert.objects.count(),
                    "today": Alert.objects.filter(triggered_at__gte=today).count(),
                    "unhandled": Alert.objects.filter(status="unhandled").count(),
                },
                "users": {
                    "total": User.objects.count(),
                    "active": User.objects.filter(is_active=True).count(),
                },
                "strategies": {
                    "total": Strategy.objects.count(),
                    "enabled": Strategy.objects.filter(enabled=True).count(),
                },
            },
            "detection": detection,
            "alertDeduplication": dedup,
            "flywheel": get_section("flywheel"),
            "settings": normalize_settings({
                "system": system,
                "detection": detection,
                "alertDeduplication": dedup,
                "flywheel": get_section("flywheel"),
                "notification": get_section("notification"),
            }),
        })

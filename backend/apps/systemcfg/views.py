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
from .services import deep_merge, get_all_settings, get_section, save_section


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
            "title": system.get("title") or "YOLOv8 视频智能分析系统",
            "logo": system.get("logo") or "",
            "version": system.get("version") or "1.0.0",
        })


class SettingsView(APIView):
    def get_permissions(self):
        if self.request.method == "PUT":
            return [IsAuthenticated(), IsAdminRole()]
        return [IsAuthenticated()]

    def get(self, request):
        return Response(get_all_settings())

    def put(self, request):
        current = get_all_settings()
        for key in ("detection", "notification", "alertDeduplication", "system"):
            if key in request.data and isinstance(request.data.get(key), dict):
                save_section(key, deep_merge(current.get(key, {}), request.data[key]))
        settings = get_all_settings()
        _publish("settings")
        return Response({"message": "设置已更新并生效", "settings": settings})


class DetectionView(APIView):
    def get_permissions(self):
        if self.request.method == "PUT":
            return [IsAuthenticated(), IsAdminOrOperator()]
        return [IsAuthenticated()]

    def get(self, request):
        return Response(get_section("detection"))

    def put(self, request):
        patch = dict(request.data)
        detection = deep_merge(get_section("detection"), patch)
        detection["confidenceThreshold"] = round(_clamp(detection.get("confidenceThreshold"), 0.1, 0.95, 0.5), 2)
        detection["iouThreshold"] = round(_clamp(detection.get("iouThreshold"), 0.1, 0.9, 0.45), 2)
        detection["fps"] = round(_clamp(detection.get("fps"), 0.5, 10, 2), 2)
        detection["maxDetections"] = int(_clamp(detection.get("maxDetections"), 10, 500, 100))
        detection["trackLostFrames"] = int(_clamp(detection.get("trackLostFrames"), 1, 100, 30))
        detection["trackingEnabled"] = bool(detection.get("trackingEnabled", True))
        categories = detection.get("categories") or []
        if not isinstance(categories, list):
            raise ValidationError("检测类别格式错误")
        detection["categories"] = [str(item) for item in categories]
        save_section("detection", detection)
        _publish("detection", {"detection": detection})
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
    def get(self, request):
        cameras = Camera.objects.all()
        today = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
        system = get_section("system")
        detection = get_section("detection")
        metrics = collect_system_metrics()
        metrics["uptime"] = _uptime_text()
        return Response({
            "system": {
                "name": system.get("title"),
                "title": system.get("title"),
                "version": system.get("version") or "1.0.0",
                "environment": "development" if dj_settings.DEBUG else "production",
                "uptime": metrics["uptime"],
                "cpu": metrics.get("cpu"),
                "memory": metrics.get("memory"),
                "gpu": metrics.get("gpu"),
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
            "alertDeduplication": get_section("alertDeduplication"),
        })

import time
from datetime import timedelta

from django.conf import settings as dj_settings
from django.db.models import Count, Q
from django.db.models.functions import TruncDate, TruncHour
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.alerts.models import Alert
from apps.alerts.serializers import AlertSerializer
from apps.cameras.models import Camera
from apps.common.sysmetrics import collect_system_metrics
from apps.inference.metrics import today_detection_stats
from apps.inference.runtime import get_all_frames, get_latest_frame
from apps.systemcfg.services import get_section


def _today():
    return timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)


def _uptime_text():
    started = getattr(dj_settings, "STARTED_AT", None) or time.time()
    delta_sec = time.time() - float(started)
    days, rem = divmod(int(delta_sec), 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    return f"{days}天 {hours}小时 {minutes}分"


class OverviewView(APIView):
    def get(self, request):
        cameras = list(Camera.objects.all())
        today = _today()
        online = sum(1 for c in cameras if c.status == "online")
        today_qs = Alert.objects.filter(triggered_at__gte=today)
        detection = today_detection_stats()
        detection["fps"] = get_section("detection").get("fps", 2)
        system = collect_system_metrics()
        system["uptime"] = _uptime_text()
        return Response({
            "cameras": {
                "total": len(cameras),
                "online": online,
                "offline": len(cameras) - online,
                "enabled": sum(1 for c in cameras if c.enabled),
                "rate": f"{(online / len(cameras) * 100) if cameras else 0:.1f}",
            },
            "alerts": {
                "today": today_qs.count(),
                "total": Alert.objects.count(),
                "unhandled": Alert.objects.filter(status="unhandled").count(),
                "resolved": Alert.objects.filter(status="resolved").count(),
            },
            "detection": detection,
            "system": system,
        })


class AlertTrendView(APIView):
    def get(self, request):
        period = request.query_params.get("period") or "day"
        tz = timezone.get_current_timezone()
        now = timezone.localtime()

        if period == "week":
            start = _today() - timedelta(days=6)
            rows = (
                Alert.objects.filter(triggered_at__gte=start)
                .annotate(bucket=TruncDate("triggered_at", tzinfo=tz))
                .values("bucket", "type")
                .annotate(c=Count("id"))
            )
            keyed = {}
            for row in rows:
                key = row["bucket"].isoformat() if row["bucket"] else ""
                keyed.setdefault(key, {"intrusion": 0, "parking": 0, "fire": 0})
                if row["type"] in keyed[key]:
                    keyed[key][row["type"]] = row["c"]
            result = []
            for i in range(6, -1, -1):
                day = (_today() - timedelta(days=i)).date()
                item = keyed.get(day.isoformat(), {"intrusion": 0, "parking": 0, "fire": 0})
                total = item["intrusion"] + item["parking"] + item["fire"]
                result.append({"date": day.isoformat(), "hour": day.strftime("%m-%d"), **item, "total": total})
            return Response(result)

        if period == "month":
            start = _today() - timedelta(days=29)
            rows = (
                Alert.objects.filter(triggered_at__gte=start)
                .annotate(bucket=TruncDate("triggered_at", tzinfo=tz))
                .values("bucket", "type")
                .annotate(c=Count("id"))
            )
            keyed = {}
            for row in rows:
                key = row["bucket"].isoformat() if row["bucket"] else ""
                keyed.setdefault(key, {"intrusion": 0, "parking": 0, "fire": 0})
                if row["type"] in keyed[key]:
                    keyed[key][row["type"]] = row["c"]
            result = []
            for i in range(29, -1, -1):
                day = (_today() - timedelta(days=i)).date()
                item = keyed.get(day.isoformat(), {"intrusion": 0, "parking": 0, "fire": 0})
                total = item["intrusion"] + item["parking"] + item["fire"]
                result.append({"date": day.isoformat(), "hour": day.strftime("%m-%d"), **item, "total": total})
            return Response(result)

        start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=23)
        rows = (
            Alert.objects.filter(triggered_at__gte=start)
            .annotate(bucket=TruncHour("triggered_at", tzinfo=tz))
            .values("bucket", "type")
            .annotate(c=Count("id"))
        )
        keyed = {}
        for row in rows:
            bucket = timezone.localtime(row["bucket"]) if row["bucket"] else None
            key = bucket.strftime("%Y-%m-%d %H:00") if bucket else ""
            keyed.setdefault(key, {"intrusion": 0, "parking": 0, "fire": 0})
            if row["type"] in keyed[key]:
                keyed[key][row["type"]] = row["c"]
        hours = []
        for i in range(23, -1, -1):
            slot = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=i)
            key = slot.strftime("%Y-%m-%d %H:00")
            item = keyed.get(key, {"intrusion": 0, "parking": 0, "fire": 0})
            hours.append({
                "hour": slot.strftime("%H:00"),
                "total": item["intrusion"] + item["parking"] + item["fire"],
                **item,
            })
        return Response(hours)


class AlertTypesView(APIView):
    def get(self, request):
        counts = {row["type"]: row["c"] for row in Alert.objects.values("type").annotate(c=Count("id"))}
        return Response([
            {"name": "区域入侵", "value": counts.get("intrusion", 0), "color": "#e74c3c"},
            {"name": "违停占道", "value": counts.get("parking", 0), "color": "#f39c12"},
            {"name": "火灾隐患", "value": counts.get("fire", 0), "color": "#e67e22"},
        ])


class AlertLevelsView(APIView):
    def get(self, request):
        counts = {row["level"]: row["c"] for row in Alert.objects.values("level").annotate(c=Count("id"))}
        return Response([
            {"name": "高危", "value": counts.get("high", 0), "color": "#f5222d"},
            {"name": "中危", "value": counts.get("medium", 0), "color": "#faad14"},
            {"name": "低危", "value": counts.get("low", 0), "color": "#52c41a"},
        ])


class CameraRankView(APIView):
    def get(self, request):
        qs = (
            Camera.objects.annotate(
                total=Count("alerts"),
                high=Count("alerts", filter=Q(alerts__level="high")),
            )
            .order_by("-total")[:10]
        )
        return Response([
            {
                "id": cam.id,
                "name": cam.name,
                "location": cam.location,
                "total": cam.total,
                "high": cam.high,
                "status": cam.status,
            }
            for cam in qs
        ])


class RecentAlertsView(APIView):
    def get(self, request):
        qs = Alert.objects.all()[:10]
        return Response(AlertSerializer(qs, many=True).data)


class AreaDistributionView(APIView):
    def get(self, request):
        cameras = Camera.objects.annotate(total=Count("alerts"))
        buckets = {"大门区域": 0, "围墙周边": 0, "地下车库": 0, "楼宇通道": 0, "中央广场": 0, "其他区域": 0}
        for cam in cameras:
            loc = cam.location or cam.name
            if "门" in loc:
                buckets["大门区域"] += cam.total
            elif "围墙" in loc:
                buckets["围墙周边"] += cam.total
            elif "库" in loc:
                buckets["地下车库"] += cam.total
            elif "楼" in loc or "通道" in loc:
                buckets["楼宇通道"] += cam.total
            elif "广场" in loc:
                buckets["中央广场"] += cam.total
            else:
                buckets["其他区域"] += cam.total
        colors = ["#f5222d", "#faad14", "#1890ff", "#52c41a", "#722ed1", "#8c8c8c"]
        return Response([
            {"name": name, "value": value, "color": colors[i]}
            for i, (name, value) in enumerate(buckets.items())
        ])


class RealtimeDetectionsView(APIView):
    def get(self, request):
        frames = get_all_frames()
        data = []
        cameras = Camera.objects.filter(status="online", enabled=True)
        camera_id = request.query_params.get("cameraId")
        if camera_id:
            cameras = cameras.filter(pk=camera_id)
        for cam in cameras:
            frame = frames.get(cam.id) or get_latest_frame(cam.id) or {}
            detections = frame.get("detections") or []
            data.append({
                "cameraId": cam.id,
                "cameraName": cam.name,
                "status": cam.status,
                "detectionCount": len(detections),
                "detections": detections,
                "timestamp": frame.get("timestamp"),
                "fps": frame.get("fps"),
            })
        return Response(data)

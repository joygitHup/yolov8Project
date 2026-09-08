import time
from datetime import timedelta

from django.conf import settings as dj_settings
from django.db.models import Count, Q
from django.db.models.functions import TruncDate, TruncHour
from django.utils import timezone

from apps.alerts.models import Alert
from apps.alerts.serializers import AlertSerializer
from apps.cameras.models import Camera
from apps.cameras.services import build_monitor_camera
from apps.common.sysmetrics import collect_system_metrics
from apps.inference.metrics import today_detection_stats
from apps.common import rdb
from apps.systemcfg.services import get_section

_CACHE = {}
_CACHE_TTL = 2.0

ALERT_TYPE_META = (
    ("intrusion", "区域入侵", "#e74c3c"),
    ("parking", "违停占道", "#f39c12"),
    ("fire", "火灾隐患", "#e67e22"),
)
ALERT_LEVEL_META = (
    ("high", "高危", "#f5222d"),
    ("medium", "中危", "#faad14"),
    ("low", "低危", "#52c41a"),
)


def _today():
    return timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)


def uptime_text():
    started = getattr(dj_settings, "STARTED_AT", None) or time.time()
    delta_sec = max(0, int(time.time() - float(started)))
    days, rem = divmod(delta_sec, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    return f"{days}天{hours}小时{minutes}分"


def _cached(key, builder):
    now = time.time()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < _CACHE_TTL:
        return hit[1]
    value = builder()
    _CACHE[key] = (now, value)
    return value


def _pct(part, whole):
    whole = float(whole or 0)
    if whole <= 0:
        return 0.0
    return round(float(part or 0) / whole * 100, 1)


def _change_rate(current, previous):
    current = float(current or 0)
    previous = float(previous or 0)
    if previous <= 0:
        return 100.0 if current > 0 else 0.0
    return round((current - previous) / previous * 100, 1)


def build_summary():
    """
    Canonical overview summary.
    Nested-only fields — avoid flat duplicates (no top-level week/total).
    """
    today = _today()
    week_start = today - timedelta(days=today.weekday())
    last_week_start = week_start - timedelta(days=7)

    cam_agg = Camera.objects.aggregate(
        total=Count("id"),
        online=Count("id", filter=Q(status="online")),
        offline=Count("id", filter=Q(status="offline")),
        enabled=Count("id", filter=Q(enabled=True)),
    )
    alert_agg = Alert.objects.aggregate(
        today=Count("id", filter=Q(triggered_at__gte=today)),
        week=Count("id", filter=Q(triggered_at__gte=week_start)),
        lastWeek=Count(
            "id",
            filter=Q(triggered_at__gte=last_week_start, triggered_at__lt=week_start),
        ),
        total=Count("id"),
        unhandled=Count("id", filter=Q(status="unhandled")),
        processing=Count("id", filter=Q(status="processing")),
        resolved=Count("id", filter=Q(status="resolved")),
        intrusion=Count("id", filter=Q(type="intrusion")),
        parking=Count("id", filter=Q(type="parking")),
        fire=Count("id", filter=Q(type="fire")),
        high=Count("id", filter=Q(level="high")),
        medium=Count("id", filter=Q(level="medium")),
        low=Count("id", filter=Q(level="low")),
    )

    total_cams = int(cam_agg["total"] or 0)
    live_n = sum(1 for item in rdb.get_all_stream_health().values() if item.get("hlsReady"))
    online = live_n
    total_alerts = int(alert_agg["total"] or 0)
    resolved = int(alert_agg["resolved"] or 0)
    week = int(alert_agg["week"] or 0)
    last_week = int(alert_agg["lastWeek"] or 0)

    cameras = {
        "total": total_cams,
        "online": online,
        "offline": max(0, total_cams - online),
        "enabled": int(cam_agg["enabled"] or 0),
        "onlineRate": _pct(online, total_cams),
        # alias kept for older dashboard cards
        "rate": f"{_pct(online, total_cams):.1f}",
    }
    alerts = {
        "today": int(alert_agg["today"] or 0),
        "week": week,
        "lastWeek": last_week,
        "weekChangeRate": _change_rate(week, last_week),
        "total": total_alerts,
        "unhandled": int(alert_agg["unhandled"] or 0),
        "processing": int(alert_agg["processing"] or 0),
        "resolved": resolved,
        "resolvedRate": _pct(resolved, total_alerts),
    }
    status_counts = {
        "unhandled": alerts["unhandled"],
        "processing": alerts["processing"],
        "resolved": alerts["resolved"],
    }
    type_counts = {
        "intrusion": int(alert_agg["intrusion"] or 0),
        "parking": int(alert_agg["parking"] or 0),
        "fire": int(alert_agg["fire"] or 0),
    }
    level_counts = {
        "high": int(alert_agg["high"] or 0),
        "medium": int(alert_agg["medium"] or 0),
        "low": int(alert_agg["low"] or 0),
    }
    return {
        "cameras": cameras,
        "alerts": alerts,
        "statusCounts": status_counts,
        "typeCounts": type_counts,
        "levelCounts": level_counts,
    }


def build_overview():
    """Dashboard overview card payload (extends summary with detection/system)."""
    summary = build_summary()
    detection = today_detection_stats()
    detection["fps"] = get_section("detection").get("fps", 2)
    system = collect_system_metrics()
    system["uptime"] = uptime_text()
    return {
        "cameras": summary["cameras"],
        "alerts": summary["alerts"],
        "statusCounts": summary["statusCounts"],
        "typeCounts": summary["typeCounts"],
        "levelCounts": summary["levelCounts"],
        "detection": detection,
        "system": system,
    }


def build_alert_stats():
    """
    GET /api/alerts/stats — same semantics as analysis.summary,
    plus dailyStats for lightweight charts.
    """
    summary = build_summary()
    today = _today()
    daily = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        nxt = day + timedelta(days=1)
        row = Alert.objects.filter(triggered_at__gte=day, triggered_at__lt=nxt).aggregate(
            total=Count("id"),
            intrusion=Count("id", filter=Q(type="intrusion")),
            parking=Count("id", filter=Q(type="parking")),
            fire=Count("id", filter=Q(type="fire")),
        )
        daily.append({
            "date": day.date().isoformat(),
            "label": day.strftime("%m-%d"),
            "total": int(row["total"] or 0),
            "intrusion": int(row["intrusion"] or 0),
            "parking": int(row["parking"] or 0),
            "fire": int(row["fire"] or 0),
        })
    return {
        "cameras": summary["cameras"],
        "alerts": summary["alerts"],
        "statusCounts": summary["statusCounts"],
        "typeCounts": summary["typeCounts"],
        "levelCounts": summary["levelCounts"],
        "dailyStats": daily,
        # Flat aliases of alerts.* for alert-center cards (no ambiguity)
        "today": summary["alerts"]["today"],
        "week": summary["alerts"]["week"],
        "total": summary["alerts"]["total"],
        "unhandled": summary["alerts"]["unhandled"],
        "processing": summary["alerts"]["processing"],
        "resolved": summary["alerts"]["resolved"],
    }


def build_alert_trend(period="day"):
    """
    Trend points always include:
      label  — X-axis text
      date   — ISO date (yyyy-mm-dd)
      hour   — HH:00 for day period, else same as label
      intrusion / parking / fire / total
    """
    period = (period or "day").lower()
    if period not in ("day", "week", "month"):
        period = "day"

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
            label = day.strftime("%m-%d")
            total = item["intrusion"] + item["parking"] + item["fire"]
            result.append({
                "label": label,
                "date": day.isoformat(),
                "hour": label,
                "intrusion": item["intrusion"],
                "parking": item["parking"],
                "fire": item["fire"],
                "total": total,
            })
        return result

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
            label = day.strftime("%m-%d")
            total = item["intrusion"] + item["parking"] + item["fire"]
            result.append({
                "label": label,
                "date": day.isoformat(),
                "hour": label,
                "intrusion": item["intrusion"],
                "parking": item["parking"],
                "fire": item["fire"],
                "total": total,
            })
        return result

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
        label = slot.strftime("%H:00")
        hours.append({
            "label": label,
            "date": slot.date().isoformat(),
            "hour": label,
            "intrusion": item["intrusion"],
            "parking": item["parking"],
            "fire": item["fire"],
            "total": item["intrusion"] + item["parking"] + item["fire"],
        })
    return hours


def build_alert_types():
    counts = {row["type"]: row["c"] for row in Alert.objects.values("type").annotate(c=Count("id"))}
    return [
        {"key": key, "type": key, "name": name, "value": int(counts.get(key, 0) or 0), "color": color}
        for key, name, color in ALERT_TYPE_META
    ]


def build_alert_levels():
    counts = {row["level"]: row["c"] for row in Alert.objects.values("level").annotate(c=Count("id"))}
    return [
        {"key": key, "level": key, "name": name, "value": int(counts.get(key, 0) or 0), "color": color}
        for key, name, color in ALERT_LEVEL_META
    ]


def build_camera_rank(limit=10):
    qs = (
        Camera.objects.annotate(
            total=Count("alerts"),
            high=Count("alerts", filter=Q(alerts__level="high")),
        )
        .order_by("-total")[:limit]
    )
    return [
        {
            "id": cam.id,
            "name": cam.name,
            "location": cam.location or "",
            "total": int(cam.total or 0),
            "high": int(cam.high or 0),
            "status": cam.status,
        }
        for cam in qs
    ]


def build_recent_alerts(limit=10):
    qs = Alert.objects.select_related("camera").all()[:limit]
    return AlertSerializer(qs, many=True).data


def build_area_distribution():
    cameras = Camera.objects.annotate(total=Count("alerts"))
    buckets = [
        ("gate", "大门区域", "#f5222d"),
        ("wall", "围墙周边", "#faad14"),
        ("garage", "地下车库", "#1890ff"),
        ("building", "楼宇通道", "#52c41a"),
        ("plaza", "中央广场", "#722ed1"),
        ("other", "其他区域", "#8c8c8c"),
    ]
    values = {k: 0 for k, _, _ in buckets}
    for cam in cameras:
        loc = cam.location or cam.name or ""
        if "门" in loc:
            values["gate"] += cam.total
        elif "围墙" in loc:
            values["wall"] += cam.total
        elif "库" in loc:
            values["garage"] += cam.total
        elif "楼" in loc or "通道" in loc:
            values["building"] += cam.total
        elif "广场" in loc:
            values["plaza"] += cam.total
        else:
            values["other"] += cam.total
    return [
        {"key": key, "name": name, "value": int(values[key] or 0), "color": color}
        for key, name, color in buckets
    ]


def build_realtime_detections(camera_id=None):
    cameras = Camera.objects.filter(status="online", enabled=True)
    if camera_id:
        cameras = cameras.filter(pk=camera_id)
    cameras = list(cameras)
    frames = rdb.get_last_frame_metas([cam.id for cam in cameras])
    data = []
    for cam in cameras:
        frame = frames.get(cam.id) or {}
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
    return data


def build_wall_cameras(limit=4):
    cameras = list(Camera.objects.filter(enabled=True).order_by("id"))
    online = [c for c in cameras if c.status == "online"]
    offline = [c for c in cameras if c.status != "online"]
    ordered = (online + offline)[:limit]
    ids = [cam.id for cam in ordered]
    streams = rdb.get_all_stream_health()
    frames = rdb.get_last_frame_metas(ids)
    return [build_monitor_camera(cam, frames, streams=streams) for cam in ordered]


def build_analysis_payload(period="day"):
    """One-shot payload for 总览分析 page."""
    period = (period or "day").lower()
    if period not in ("day", "week", "month"):
        period = "day"

    def _build():
        summary = build_summary()
        return {
            "summary": summary,
            # Convenience mirrors (same objects as summary.*) for short bindings
            "cameras": summary["cameras"],
            "alerts": summary["alerts"],
            "statusCounts": summary["statusCounts"],
            "typeCounts": summary["typeCounts"],
            "levelCounts": summary["levelCounts"],
            "trendPeriod": period,
            "alertTrend": build_alert_trend(period),
            "alertTypes": build_alert_types(),
            "alertLevels": build_alert_levels(),
            "cameraRank": build_camera_rank(),
            "recentAlerts": build_recent_alerts(8),
            "areaDistribution": build_area_distribution(),
            "serverTime": timezone.localtime().isoformat(),
        }

    return _cached(f"analysis:{period}", _build)


def build_screen_payload():
    def _build():
        overview = build_overview()
        return {
            "overview": overview,
            "alertTrend": build_alert_trend("day"),
            "alertTypes": build_alert_types(),
            "alertLevels": build_alert_levels(),
            "cameraRank": build_camera_rank(),
            "recentAlerts": build_recent_alerts(),
            "areaDistribution": build_area_distribution(),
            "realtimeDetections": build_realtime_detections(),
            "cameras": build_wall_cameras(4),
            "serverTime": timezone.localtime().isoformat(),
        }

    return _cached("screen", _build)

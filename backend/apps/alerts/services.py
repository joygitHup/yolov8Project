import html
from datetime import datetime, time, timedelta

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from .models import AlertAction, AlertTicket

_TYPE_TEXT = {"intrusion": "区域入侵", "parking": "违停占道", "fire": "火灾隐患"}
_LEVEL_TEXT = {"high": "高危", "medium": "中危", "low": "低危"}
_STATUS_TEXT = {"unhandled": "待处理", "processing": "处理中", "resolved": "已处理"}
_LABEL_TEXT = {
    "person": "人", "car": "轿车", "truck": "卡车", "fire": "火焰",
    "smoke": "烟雾", "bicycle": "自行车", "motorcycle": "摩托车",
}
_BOX_COLOR = {
    "person": "#52c41a", "car": "#3b82f6", "truck": "#8b5cf6",
    "fire": "#f5222d", "smoke": "#f59e0b",
}


def parse_query_dt(value, end=False):
    if not value:
        return None
    raw = str(value).strip()
    dt = parse_datetime(raw.replace(" ", "T"))
    if dt is None and len(raw) >= 10:
        day = parse_date(raw[:10])
        if day:
            dt = datetime.combine(day, time.max if end else time.min)
    if dt is None:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def iso(value):
    if not value:
        return None
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    return timezone.localtime(value).isoformat()


def serialize_camera(camera):
    if not camera:
        return None
    return {
        "id": camera.id,
        "name": camera.name,
        "location": camera.location,
        "ip": camera.ip,
        "type": camera.type,
        "status": camera.status,
        "enabled": camera.enabled,
        "resolution": camera.resolution,
        "rtsp": camera.rtsp,
    }


def serialize_action(action):
    return {
        "id": action.id,
        "action": action.action,
        "operator": action.operator,
        "fromStatus": action.from_status,
        "toStatus": action.to_status,
        "note": action.note,
        "createdAt": iso(action.created_at),
    }


def serialize_ticket(ticket):
    if not ticket:
        return None
    return {
        "id": ticket.id,
        "title": ticket.title,
        "assignee": ticket.assignee,
        "status": ticket.status,
        "note": ticket.note,
        "createdBy": ticket.created_by,
        "createdAt": iso(ticket.created_at),
        "updatedAt": iso(ticket.updated_at),
    }


def build_clip(alert):
    triggered = alert.triggered_at or timezone.now()
    start = triggered - timedelta(seconds=5)
    end = triggered + timedelta(seconds=10)
    return {
        "available": False,
        "duration": 15,
        "startedAt": iso(start),
        "endedAt": iso(end),
        "message": "暂未接入录像文件，已根据告警时间生成 15 秒片段窗口",
    }


def _boxes(alert):
    boxes = []
    for item in alert.detection_boxes or []:
        bbox = item.get("bbox") if isinstance(item, dict) and "bbox" in item else item
        if not isinstance(bbox, dict):
            continue
        boxes.append({
            "x": float(bbox.get("x") or 0),
            "y": float(bbox.get("y") or 0),
            "w": float(bbox.get("w") or 0),
            "h": float(bbox.get("h") or 0),
            "label": item.get("label") or bbox.get("label") or "object",
            "confidence": float(item.get("confidence") or bbox.get("confidence") or 0),
        })
    return boxes


def build_evidence_svg(alert, width=1280, height=720):
    camera = alert.camera
    hue = ((camera.id if camera else alert.id or 1) * 47) % 360
    name = html.escape(alert.camera_name or (camera.name if camera else "未知摄像头"))
    location = html.escape((camera.location if camera else "") or "")
    ip = html.escape((camera.ip if camera else "") or "")
    triggered = html.escape(timezone.localtime(alert.triggered_at).strftime("%Y-%m-%d %H:%M:%S") if alert.triggered_at else "")
    type_text = html.escape(_TYPE_TEXT.get(alert.type, alert.type or ""))
    boxes = _boxes(alert)
    rects = []
    for box in boxes:
        color = _BOX_COLOR.get(box["label"], "#52c41a")
        x = box["x"] * width
        y = box["y"] * height
        w = box["w"] * width
        h = box["h"] * height
        label = html.escape(_LABEL_TEXT.get(box["label"], box["label"]))
        conf = box["confidence"]
        pct = conf * 100 if conf <= 1 else conf
        rects.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'fill="none" stroke="{color}" stroke-width="3"/>'
            f'<rect x="{x:.1f}" y="{max(y - 28, 0):.1f}" width="{max(w, 90):.1f}" height="24" fill="{color}"/>'
            f'<text x="{x + 6:.1f}" y="{max(y - 11, 16):.1f}" fill="#fff" font-size="16" font-family="sans-serif">'
            f'{label} {pct:.0f}%</text>'
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">'
        f'<defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="#1e293b"/><stop offset="100%" stop-color="#0f172a"/>'
        f'</linearGradient></defs>'
        f'<rect width="100%" height="100%" fill="url(#bg)"/>'
        f'<ellipse cx="360" cy="220" rx="280" ry="160" fill="hsla({hue},70%,45%,0.28)"/>'
        + "".join(rects) +
        f'<text x="24" y="40" fill="#fff" font-size="22" font-family="sans-serif" font-weight="700">{name}</text>'
        f'<text x="24" y="68" fill="#cbd5e1" font-size="16" font-family="sans-serif">'
        f'{location} {ip} · {type_text} · {triggered}</text>'
        f'<text x="24" y="{height - 24}" fill="#94a3b8" font-size="14" font-family="sans-serif">'
        f'检测目标 {len(boxes)} · 置信度 {alert.confidence:.2f}</text>'
        f'</svg>'
    )


def log_action(alert, operator, action, from_status, to_status, note=""):
    return AlertAction.objects.create(
        alert=alert,
        operator=operator or "",
        action=action,
        from_status=from_status or "",
        to_status=to_status or "",
        note=note or "",
    )


def create_or_get_ticket(alert, operator, note="", assignee=""):
    existing = AlertTicket.objects.filter(alert=alert).first()
    if existing:
        return existing, False
    title = f"{_TYPE_TEXT.get(alert.type, alert.type)} · {alert.camera_name or '未知设备'}"
    ticket = AlertTicket.objects.create(
        alert=alert,
        title=title,
        assignee=assignee or "",
        note=note or "",
        created_by=operator or "",
        status="open",
    )
    log_action(alert, operator, "dispatch", alert.status, alert.status, note or "已派发工单")
    return ticket, True

import logging
import random
import threading
import time
from django.db import close_old_connections
from django.utils import timezone
from apps.alerts.models import Alert
from apps.alerts.serializers import AlertSerializer
from apps.cameras.models import Camera
from apps.inference.metrics import flush_metrics, record_frame
from apps.inference.notify import dispatch
from apps.inference.runtime import set_frame
from apps.inference.strategy import match_strategy
from apps.realtime.broadcast import broadcast
from apps.systemcfg.services import get_section

logger = logging.getLogger("inference")

_LABEL_TYPE = {
    "person": "intrusion",
    "car": "parking",
    "truck": "parking",
    "bus": "parking",
    "bicycle": "parking",
    "motorcycle": "parking",
    "fire": "fire",
    "smoke": "fire",
}
_TYPE_DESC = {
    "intrusion": "检测到人员进入警戒区域",
    "parking": "禁停区域发现车辆滞留",
    "fire": "检测到明火或烟雾",
}
_dedup = {}
_stop = threading.Event()
_thread = None
_tracks = {}
_next_track_id = 1


def _iou(a, b):
    x1 = max(a["x"], b["x"])
    y1 = max(a["y"], b["y"])
    x2 = min(a["x"] + a["w"], b["x"] + b["w"])
    y2 = min(a["y"] + a["h"], b["y"] + b["h"])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    union = a["w"] * a["h"] + b["w"] * b["h"] - inter
    return 0 if union <= 0 else inter / union


def _nms(boxes, threshold):
    ordered = sorted(boxes, key=lambda x: x["confidence"], reverse=True)
    kept = []
    for box in ordered:
        if all(_iou(box, k) < threshold for k in kept):
            kept.append(box)
    return kept


def infer_frame(camera, params):
    categories = params.get("categories") or []
    if not categories:
        return []
    max_det = int(params.get("maxDetections") or 100)
    conf_min = float(params.get("confidenceThreshold") or 0.5)
    iou_thr = float(params.get("iouThreshold") or 0.45)
    raw = []
    for i in range(random.randint(0, min(5, max_det))):
        raw.append({
            "id": i,
            "label": random.choice(categories),
            "confidence": round(0.35 + random.random() * 0.6, 2),
            "bbox": {
                "x": round(random.random() * 0.8, 4),
                "y": round(random.random() * 0.7, 4),
                "w": round(0.1 + random.random() * 0.2, 4),
                "h": round(0.15 + random.random() * 0.25, 4),
            },
        })
    filtered = [d for d in raw if d["confidence"] >= conf_min]
    boxes = [{"x": d["bbox"]["x"], "y": d["bbox"]["y"], "w": d["bbox"]["w"], "h": d["bbox"]["h"],
              "confidence": d["confidence"], "label": d["label"]} for d in filtered]
    kept = _nms(boxes, iou_thr)[:max_det]
    return [
        {"id": i, "label": b["label"], "confidence": b["confidence"],
         "bbox": {"x": b["x"], "y": b["y"], "w": b["w"], "h": b["h"]}}
        for i, b in enumerate(kept)
    ]


def apply_tracking(camera_id, detections, params):
    global _next_track_id
    if not params.get("trackingEnabled", True):
        return detections
    max_lost = int(params.get("trackLostFrames") or 30)
    state = _tracks.setdefault(int(camera_id), {})
    for track in state.values():
        track["lost"] += 1
    assigned = set()
    for det in detections:
        bbox = det.get("bbox") or {}
        best_id, best_iou = None, 0.3
        for tid, track in state.items():
            if tid in assigned:
                continue
            score = _iou(bbox, track["bbox"])
            if score > best_iou:
                best_id, best_iou = tid, score
        if best_id is not None:
            det["trackId"] = best_id
            state[best_id] = {"bbox": bbox, "lost": 0}
            assigned.add(best_id)
        else:
            tid = _next_track_id
            _next_track_id += 1
            det["trackId"] = tid
            state[tid] = {"bbox": bbox, "lost": 0}
            assigned.add(tid)
    _tracks[int(camera_id)] = {tid: item for tid, item in state.items() if item["lost"] <= max_lost}
    return detections


def _deduped(camera_id, alert_type):
    settings = get_section("alertDeduplication") or {"enabled": True, "interval": 30}
    if not settings.get("enabled", True):
        return False
    key = f"{camera_id}:{alert_type}"
    last = _dedup.get(key)
    now = time.time()
    interval = int(settings.get("interval") or 30)
    if last and now - last < interval:
        return True
    _dedup[key] = now
    return False


def _maybe_alert(camera, detections):
    grouped = {}
    for det in detections:
        alert_type = _LABEL_TYPE.get(det["label"])
        if not alert_type or alert_type not in (camera.detection_types or []):
            continue
        grouped.setdefault(alert_type, []).append(det)
    for alert_type, boxes in grouped.items():
        strategy = match_strategy(camera, alert_type)
        if not strategy or _deduped(camera.id, alert_type):
            continue
        best = max(boxes, key=lambda x: x["confidence"])
        level = "high" if alert_type == "fire" else (strategy.alert_level or "medium")
        alert = Alert.objects.create(
            camera=camera,
            camera_name=camera.name,
            type=alert_type,
            level=level,
            description=_TYPE_DESC[alert_type],
            status="unhandled",
            confidence=best["confidence"],
            snapshot_url="",
            image_url="",
            video_url="",
            detection_boxes=[{"x": b["bbox"]["x"], "y": b["bbox"]["y"], "w": b["bbox"]["w"], "h": b["bbox"]["h"],
                              "label": b["label"], "confidence": b["confidence"]} for b in boxes],
            triggered_at=timezone.now(),
        )
        alert.snapshot_url = f"/api/alerts/{alert.id}/evidence"
        alert.image_url = alert.snapshot_url
        alert.save(update_fields=["snapshot_url", "image_url"])
        payload = AlertSerializer(alert).data
        broadcast("alert:created", payload)
        dispatch(alert)


def _loop():
    logger.info("YOLOv8 推理流水线已启动（模拟 Worker，策略/去重生效）")
    while not _stop.wait(0.2):
        close_old_connections()
        params = get_section("detection")
        fps = max(0.5, float(params.get("fps") or 2))
        interval = max(0.3, 1.0 / fps)
        cameras = list(Camera.objects.filter(enabled=True, status="online"))
        for camera in cameras:
            detections = apply_tracking(camera.id, infer_frame(camera, params), params)
            frame = {
                "cameraId": camera.id,
                "timestamp": timezone.now().isoformat(),
                "fps": fps,
                "detections": detections,
            }
            set_frame(camera.id, frame)
            try:
                record_frame(camera.id, detections)
            except Exception:
                logger.exception("record_frame failed")
            broadcast("detection:frame", frame)
            if random.random() < 0.08:
                _maybe_alert(camera, detections)
        try:
            flush_metrics()
        except Exception:
            logger.exception("flush_metrics failed")
        _stop.wait(interval)


def start_pipeline():
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="yolo-pipeline", daemon=True)
    _thread.start()

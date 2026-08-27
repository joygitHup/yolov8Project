import time
from collections import defaultdict
from django.db import close_old_connections
from django.db.models import F
from django.utils import timezone

_buffer = defaultdict(lambda: {"frame_count": 0, "box_count": 0, "confidence_sum": 0.0})
_last_flush = 0.0


def record_frame(camera_id, detections):
    key = (timezone.localdate(), int(camera_id))
    item = _buffer[key]
    item["frame_count"] += 1
    item["box_count"] += len(detections or [])
    item["confidence_sum"] += sum(float(d.get("confidence") or 0) for d in (detections or []))


def flush_metrics(force=False):
    global _last_flush
    now = time.time()
    if not force and now - _last_flush < 5 and _buffer:
        return
    if not _buffer:
        _last_flush = now
        return
    from apps.inference.models import DetectionMetric
    from apps.cameras.models import Camera

    close_old_connections()
    snapshot = dict(_buffer)
    _buffer.clear()
    _last_flush = now
    try:
        for (day, camera_id), vals in snapshot.items():
            camera = Camera.objects.filter(pk=camera_id).first()
            if not camera:
                continue
            obj, created = DetectionMetric.objects.get_or_create(
                date=day,
                camera=camera,
                defaults=vals,
            )
            if not created:
                DetectionMetric.objects.filter(pk=obj.pk).update(
                    frame_count=F("frame_count") + vals["frame_count"],
                    box_count=F("box_count") + vals["box_count"],
                    confidence_sum=F("confidence_sum") + vals["confidence_sum"],
                )
    except Exception:
        for key, vals in snapshot.items():
            existing = _buffer[key]
            existing["frame_count"] += vals["frame_count"]
            existing["box_count"] += vals["box_count"]
            existing["confidence_sum"] += vals["confidence_sum"]
        raise


def today_detection_stats():
    from django.db.models import Sum
    from apps.inference.models import DetectionMetric

    close_old_connections()
    flush_metrics(force=True)
    agg = DetectionMetric.objects.filter(date=timezone.localdate()).aggregate(
        frames=Sum("frame_count"),
        boxes=Sum("box_count"),
        conf=Sum("confidence_sum"),
    )
    boxes = int(agg.get("boxes") or 0)
    conf = float(agg.get("conf") or 0)
    frames = int(agg.get("frames") or 0)
    if boxes == 0:
        from apps.inference.runtime import get_all_frames
        live_boxes = 0
        live_conf = 0.0
        live_frames = 0
        for frame in get_all_frames().values():
            dets = frame.get("detections") or []
            live_frames += 1
            live_boxes += len(dets)
            live_conf += sum(float(d.get("confidence") or 0) for d in dets)
        boxes = live_boxes
        conf = live_conf
        frames = live_frames
    return {
        "totalToday": boxes,
        "framesToday": frames,
        "avgConfidence": f"{(conf / boxes):.2f}" if boxes else "0.00",
    }

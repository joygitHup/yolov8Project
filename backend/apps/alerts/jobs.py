"""Queue handlers for snapshot / short clip evidence."""
from __future__ import annotations

import logging

from apps.common.jobs import QUEUE_EVIDENCE, Requeue, enqueue, register

logger = logging.getLogger("alerts.jobs")


def enqueue_evidence(alert_id: int, rtsp: str, boxes, camera_id: int | None = None) -> None:
    payload = {
        "alertId": int(alert_id),
        "rtsp": rtsp or "",
        "boxes": boxes or [],
        "cameraId": int(camera_id) if camera_id else 0,
    }
    enqueue(QUEUE_EVIDENCE, "capture_snapshot", payload)
    enqueue(QUEUE_EVIDENCE, "capture_clip", payload)


@register("capture_snapshot")
def job_capture_snapshot(payload: dict) -> None:
    from apps.alerts.evidence import capture_snapshot
    from apps.alerts.models import Alert
    from apps.alerts.serializers import AlertSerializer
    from apps.realtime.broadcast import broadcast

    alert_id = int(payload.get("alertId") or 0)
    alert = Alert.objects.filter(pk=alert_id).first()
    if not alert:
        return
    snap = (alert.snapshot_url or "").strip()
    if snap.startswith("/media/alerts/"):
        return
    camera_id = int(payload.get("cameraId") or 0) or (alert.camera_id or 0)
    jpeg = None
    raw = payload.get("frameJpeg") or ""
    if raw:
        import base64

        try:
            jpeg = base64.b64decode(raw)
        except Exception:
            jpeg = None
    url = capture_snapshot(
        alert.id,
        payload.get("rtsp") or (alert.camera.rtsp if alert.camera else "") or "",
        payload.get("boxes") or alert.detection_boxes,
        camera_id=camera_id,
        jpeg=jpeg,
    )
    if not url:
        raise RuntimeError(f"snapshot failed alert={alert_id}")
    alert.snapshot_url = url
    alert.image_url = url
    alert.save(update_fields=["snapshot_url", "image_url"])
    try:
        broadcast("alert:updated", AlertSerializer(alert).data)
    except Exception:
        logger.exception("broadcast snapshot failed alert=%s", alert_id)


@register("capture_clip")
def job_capture_clip(payload: dict) -> None:
    from apps.alerts.evidence import capture_clip
    from apps.alerts.models import Alert
    from apps.alerts.serializers import AlertSerializer
    from apps.common import rdb
    from apps.realtime.broadcast import broadcast

    alert_id = int(payload.get("alertId") or 0)
    alert = Alert.objects.filter(pk=alert_id).first()
    if not alert:
        return
    video = (alert.video_url or "").strip()
    if video.startswith("/media/alerts/"):
        return
    camera_id = int(payload.get("cameraId") or 0) or (alert.camera_id or 0)
    rtsp = payload.get("rtsp") or (alert.camera.rtsp if alert.camera else "") or ""
    if camera_id and not rdb.acquire_clip_lock(camera_id, ttl=25):
        waits = int(payload.get("_waits") or 0) + 1
        if waits > 20:
            raise RuntimeError(f"clip lock timeout alert={alert_id}")
        payload["_waits"] = waits
        raise Requeue(delay=3.0, count_attempt=False)
    try:
        url = capture_clip(alert.id, rtsp, camera_id=camera_id)
    finally:
        if camera_id:
            rdb.release_clip_lock(camera_id)
    if not url:
        raise RuntimeError(f"clip failed alert={alert_id}")
    alert.video_url = url
    alert.save(update_fields=["video_url"])
    try:
        broadcast("alert:updated", AlertSerializer(alert).data)
    except Exception:
        logger.exception("broadcast clip failed alert=%s", alert_id)

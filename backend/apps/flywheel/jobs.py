"""Persist a sampled JPEG + YOLO label file to MinIO."""
from __future__ import annotations

import logging
import random
import time
import uuid

from apps.common import storage
from apps.common.jobs import Requeue, register
from apps.flywheel.capture import grab_rtsp_jpeg
from apps.flywheel.dataset import (
    DATA_YAML_KEY,
    IMAGES_PREFIX,
    LABELS_PREFIX,
    boxes_to_yolo_txt,
    canonical_boxes,
    class_names,
    render_data_yaml,
)
from apps.flywheel.models import FlywheelSample
from apps.flywheel.services import approve_sample
from apps.systemcfg.services import get_section

logger = logging.getLogger("flywheel.jobs")


@register("flywheel.yaml")
def job_write_yaml(_payload: dict) -> None:
    storage.put_key(DATA_YAML_KEY, render_data_yaml().encode("utf-8"), "text/yaml")


def _resolve_rtsp(camera_id: int, payload: dict) -> str:
    rtsp = (payload.get("rtsp") or "").strip()
    if rtsp:
        return rtsp
    from apps.cameras.models import Camera

    cam = Camera.objects.filter(pk=int(camera_id)).only("rtsp").first()
    return ((cam.rtsp if cam else "") or "").strip()


@register("flywheel.sample")
def job_sample(payload: dict) -> None:
    camera_id = int(payload.get("cameraId") or 0)
    if not camera_id:
        return

    rtsp = _resolve_rtsp(camera_id, payload)
    jpeg = grab_rtsp_jpeg(rtsp, quality=95, camera_id=camera_id) if (rtsp or camera_id) else None
    if not jpeg:
        # Last-resort fallback so a brief RTSP blip does not drop the sample forever
        from apps.common import rdb
        import base64

        jpeg = rdb.get_last_frame_jpeg(camera_id)
        if not jpeg:
            raw = payload.get("frameJpeg") or ""
            if raw:
                try:
                    jpeg = base64.b64decode(raw)
                except Exception:
                    jpeg = None
        if jpeg:
            logger.warning(
                "flywheel sample camera=%s used redis/payload fallback (rtsp grab failed)",
                camera_id,
            )
    if not jpeg:
        raise Requeue(delay=2.0)

    source = str(payload.get("source") or "uncertain")
    if source not in ("alert", "uncertain"):
        source = "uncertain"
    names = class_names()
    boxes = canonical_boxes(payload.get("boxes") or [], names)
    txt, box_count = boxes_to_yolo_txt(boxes, names)
    stem = f"{camera_id}_{int(time.time() * 1000)}_{source}_{uuid.uuid4().hex[:8]}"
    image_key = f"{IMAGES_PREFIX}/{stem}.jpg"
    label_key = f"{LABELS_PREFIX}/{stem}.txt"
    if not storage.put_key(image_key, jpeg, "image/jpeg"):
        raise RuntimeError(f"flywheel image put failed {image_key}")
    label_bytes = (txt or "").encode("utf-8") or b"\n"
    if storage.put_key(label_key, label_bytes, "text/plain") is None:
        raise RuntimeError(f"flywheel label put failed {label_key}")
    storage.put_key(DATA_YAML_KEY, render_data_yaml(names).encode("utf-8"), "text/yaml")

    try:
        max_conf = float(payload.get("maxConf") or 0)
    except (TypeError, ValueError):
        max_conf = 0.0
    alert_id = int(payload.get("alertId") or 0) or None
    sample = FlywheelSample.objects.create(
        camera_id=camera_id,
        source=source,
        status="pending",
        alert_id=alert_id,
        stem=stem,
        image_key=image_key,
        label_key=label_key,
        boxes=boxes,
        max_conf=max_conf,
        box_count=box_count,
    )
    cfg = get_section("flywheel")
    try:
        auto_min = float(cfg.get("autoLabelMin") or 0.7)
    except (TypeError, ValueError):
        auto_min = 0.7
    # High-confidence alert frames skip the desk unless they hit the 10% spot-check.
    if cfg.get("autoApproveAlerts") and source == "alert" and max_conf >= auto_min and random.random() >= 0.1:
        try:
            approve_sample(sample, boxes, operator="auto")
        except Exception:
            logger.exception("flywheel auto-approve failed stem=%s", stem)
    logger.info(
        "flywheel saved camera=%s source=%s status=%s boxes=%s stem=%s bytes=%s rtsp=%s",
        camera_id,
        source,
        sample.status,
        box_count,
        stem,
        len(jpeg),
        bool(rtsp),
    )


@register("flywheel.train")
def job_train(payload: dict) -> None:
    run_id = int(payload.get("runId") or 0)
    if not run_id:
        return
    from apps.flywheel.trainer import run_train_job

    run_train_job(run_id)

"""Ingest-side flywheel sampling: enqueue alert + uncertain frames."""
from __future__ import annotations

import logging

from apps.common import rdb
from apps.common.jobs import QUEUE_FLYWHEEL, enqueue
from apps.systemcfg.services import get_section

logger = logging.getLogger("flywheel")


def _cfg():
    return get_section("flywheel") or {}


def on_frame(camera_id: int, detections, rtsp: str = "") -> None:
    cfg = _cfg()
    if not cfg.get("enabled") or not cfg.get("uncertainFrames"):
        return
    dets = [d for d in (detections or []) if isinstance(d, dict)]
    if not dets:
        return
    try:
        scores = [float(d.get("confidence") or 0) for d in dets]
    except (TypeError, ValueError):
        return
    max_conf = max(scores) if scores else 0.0
    low = float(cfg.get("uncertainLow") or 0.25)
    high = float(cfg.get("uncertainHigh") or 0.55)
    auto_min = float(cfg.get("autoLabelMin") or 0.7)
    # YOLO 侧通常已按检测阈值过滤，上限至少覆盖到自动通过阈值，否则难例几乎采不到。
    high = max(high, auto_min)
    if max_conf < low or max_conf > high:
        return
    if not rdb.flywheel_allow(
        camera_id,
        int(cfg.get("sampleIntervalSec") or 15),
        int(cfg.get("quotaPerCameraHour") or 40),
        force=False,
    ):
        return
    enqueue(
        QUEUE_FLYWHEEL,
        "flywheel.sample",
        {
            "cameraId": int(camera_id),
            "rtsp": (rtsp or "").strip(),
            "source": "uncertain",
            "boxes": dets,
            "maxConf": max_conf,
        },
    )


def on_alert(camera_id: int, alert, rtsp: str = "") -> None:
    cfg = _cfg()
    if not cfg.get("enabled") or not cfg.get("alertFrames"):
        return
    rdb.flywheel_allow(
        camera_id,
        0,
        int(cfg.get("quotaPerCameraHour") or 40),
        force=True,
    )
    try:
        max_conf = float(getattr(alert, "confidence", 0) or 0)
    except (TypeError, ValueError):
        max_conf = 0.0
    enqueue(
        QUEUE_FLYWHEEL,
        "flywheel.sample",
        {
            "cameraId": int(camera_id),
            "rtsp": (rtsp or "").strip(),
            "source": "alert",
            "alertId": int(getattr(alert, "id", 0) or 0),
            "boxes": list(getattr(alert, "detection_boxes", None) or []),
            "maxConf": max_conf,
        },
    )

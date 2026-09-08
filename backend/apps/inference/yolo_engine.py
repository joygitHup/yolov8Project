"""Ultralytics YOLOv8 engine — singleton load of local trained weights."""
from __future__ import annotations

import logging
import os
import threading
from typing import Any

from apps.systemcfg.defaults import DEFAULT_YOLO_WEIGHTS

logger = logging.getLogger("inference.yolo")

_lock = threading.Lock()
_model = None
_model_path: str | None = None
_load_error: str | None = None


def _env_enabled() -> bool:
    raw = os.environ.get("YOLO_INFER_ENABLED", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _resolve_weights(path: str | None = None) -> str:
    candidate = (path or os.environ.get("YOLO_WEIGHTS") or DEFAULT_YOLO_WEIGHTS or "").strip()
    return candidate


def _resolve_device() -> str:
    return (os.environ.get("YOLO_DEVICE") or "cpu").strip() or "cpu"


def get_load_error() -> str | None:
    return _load_error


def is_ready() -> bool:
    return _model is not None and _env_enabled()


def reload_model(path: str | None = None) -> bool:
    """Force reload weights. Returns True on success."""
    global _model, _model_path, _load_error
    with _lock:
        _model = None
        _model_path = None
        _load_error = None
        return _ensure_model_locked(path)


def _ensure_model_locked(path: str | None = None) -> bool:
    global _model, _model_path, _load_error
    if not _env_enabled():
        _load_error = "YOLO_INFER_ENABLED is off"
        return False
    weights = _resolve_weights(path)
    if _model is not None and _model_path == weights:
        return True
    if not weights or not os.path.isfile(weights):
        _load_error = f"weights not found: {weights}"
        logger.error(_load_error)
        return False
    try:
        from ultralytics import YOLO

        logger.info("Loading YOLO weights: %s (device=%s)", weights, _resolve_device())
        model = YOLO(weights)
        # warm-up / bind device lazily on first predict
        _model = model
        _model_path = weights
        _load_error = None
        logger.info("YOLO loaded: %s", weights)
        return True
    except Exception as exc:
        _model = None
        _model_path = None
        _load_error = str(exc)
        logger.exception("Failed to load YOLO: %s", exc)
        return False


def ensure_model(path: str | None = None) -> bool:
    with _lock:
        return _ensure_model_locked(path)


def predict(
    frame_bgr,
    *,
    conf: float = 0.5,
    iou: float = 0.45,
    max_det: int = 100,
    model_path: str | None = None,
) -> list[dict[str, Any]]:
    """
    Run detection on a BGR numpy frame.
    Returns canonical detections:
      { id, label, confidence, bbox: {x,y,w,h} }  with coords in 0~1
    """
    if frame_bgr is None:
        return []
    if not ensure_model(model_path):
        return []

    h, w = frame_bgr.shape[:2]
    if h <= 0 or w <= 0:
        return []

    device = _resolve_device()
    try:
        with _lock:
            results = _model.predict(
                source=frame_bgr,
                conf=float(conf),
                iou=float(iou),
                max_det=int(max_det),
                device=device,
                verbose=False,
            )
    except Exception as exc:
        logger.exception("YOLO predict failed: %s", exc)
        return []

    if not results:
        return []

    result = results[0]
    names = result.names or {}
    boxes = result.boxes
    if boxes is None or len(boxes) == 0:
        return []

    out: list[dict[str, Any]] = []
    xyxy = boxes.xyxy.cpu().numpy()
    confs = boxes.conf.cpu().numpy()
    clss = boxes.cls.cpu().numpy().astype(int)
    for i, (box, score, cls_id) in enumerate(zip(xyxy, confs, clss)):
        x1, y1, x2, y2 = [float(v) for v in box]
        bw = max(0.0, x2 - x1)
        bh = max(0.0, y2 - y1)
        label = names.get(int(cls_id), str(cls_id))
        out.append({
            "id": i + 1,
            "label": str(label),
            "confidence": round(float(score), 4),
            "bbox": {
                "x": round(x1 / w, 4),
                "y": round(y1 / h, 4),
                "w": round(bw / w, 4),
                "h": round(bh / h, 4),
            },
        })
    return out[: max(1, int(max_det))]

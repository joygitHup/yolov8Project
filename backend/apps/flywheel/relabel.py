"""Fix flywheel boxes that mapped bus/bike/moto onto 轿车."""
from __future__ import annotations

import logging
import threading

from apps.systemcfg.model_names import VEHICLE_SUPERCLASS

logger = logging.getLogger("flywheel.relabel")

_VEHICLE_HINTS = {name.lower() for name in VEHICLE_SUPERCLASS} | {
    "bus",
    "bicycle",
    "motorcycle",
    "bike",
    "motorbike",
}


def schedule_repair(*, force: bool = False) -> None:
    threading.Thread(
        target=repair_mislabelled_samples,
        kwargs={"force": force},
        name="flywheel-relabel",
        daemon=True,
    ).start()


def repair_mislabelled_samples(*, force: bool = False) -> dict:
    from apps.alerts.models import Alert
    from apps.flywheel.dataset import canonical_boxes, class_names
    from apps.flywheel.models import FlywheelSample
    from apps.flywheel.services import write_auto_labels, write_reviewed

    names = class_names()
    sig = ",".join(names)
    if not _claim(sig, force=force):
        return {"skipped": True, "reason": "lock"}

    scanned = 0
    changed = 0
    alert_ids = set()
    samples = list(
        FlywheelSample.objects.exclude(status="discarded").only(
            "id", "status", "alert_id", "boxes", "label_key", "reviewed_label_key",
            "reviewed_image_key", "image_key", "box_count",
        )
    )
    for sample in samples:
        if sample.alert_id:
            alert_ids.add(int(sample.alert_id))
    alerts = {}
    if alert_ids:
        for row in Alert.objects.filter(pk__in=alert_ids).only("id", "detection_boxes"):
            alerts[row.id] = row.detection_boxes if isinstance(row.detection_boxes, list) else []

    for sample in samples:
        scanned += 1
        raw = sample.boxes if isinstance(sample.boxes, list) else []
        hinted = _apply_alert_hints(raw, alerts.get(int(sample.alert_id or 0)) or [])
        boxes = canonical_boxes(hinted, names)
        if _labels_of(raw) == _labels_of(boxes):
            continue
        try:
            write_auto_labels(sample, boxes)
            fields = ["boxes", "box_count"]
            if sample.status == "approved":
                try:
                    write_reviewed(sample, boxes)
                    fields.extend(["reviewed_image_key", "reviewed_label_key"])
                except Exception:
                    logger.exception("reviewed relabel failed id=%s", sample.id)
            sample.save(update_fields=list(dict.fromkeys(fields)))
            changed += 1
        except Exception:
            logger.exception("flywheel relabel failed id=%s", sample.id)

    logger.info("flywheel relabel scanned=%s changed=%s names=%s", scanned, changed, len(names))
    _mark_done(sig)
    return {"scanned": scanned, "changed": changed, "skipped": False}


def _claim(sig: str, *, force: bool) -> bool:
    from apps.common import rdb

    client = rdb.get_client()
    lock_key = rdb.prefix("flywheel", "relabel", "lock")
    done_key = rdb.prefix("flywheel", "relabel", "done")
    if client is None:
        return True
    try:
        if not force:
            previous = client.get(done_key)
            if previous == sig.encode("utf-8"):
                return False
        got = client.set(lock_key, b"1", nx=True, ex=1800)
        return bool(got)
    except Exception:
        return True


def _mark_done(sig: str) -> None:
    from apps.common import rdb

    client = rdb.get_client()
    if client is None:
        return
    try:
        client.set(rdb.prefix("flywheel", "relabel", "done"), sig.encode("utf-8"), ex=7 * 24 * 3600)
        client.delete(rdb.prefix("flywheel", "relabel", "lock"))
    except Exception:
        pass


def _labels_of(boxes) -> list[str]:
    out = []
    for item in boxes or []:
        if not isinstance(item, dict):
            continue
        out.append(str(item.get("label") or "").strip())
    return out


def _bbox(item) -> dict | None:
    if not isinstance(item, dict):
        return None
    bbox = item.get("bbox") if isinstance(item.get("bbox"), dict) else item
    if not isinstance(bbox, dict):
        return None
    try:
        return {
            "x": float(bbox.get("x") or 0),
            "y": float(bbox.get("y") or 0),
            "w": float(bbox.get("w") or 0),
            "h": float(bbox.get("h") or 0),
        }
    except (TypeError, ValueError):
        return None


def _iou(a, b) -> float:
    x1 = max(a["x"], b["x"])
    y1 = max(a["y"], b["y"])
    x2 = min(a["x"] + a["w"], b["x"] + b["w"])
    y2 = min(a["y"] + a["h"], b["y"] + b["h"])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = a["w"] * a["h"] + b["w"] * b["h"] - inter
    return 0.0 if union <= 0 else inter / union


def _is_vehicle_hint(label: str) -> bool:
    text = str(label or "").strip()
    if not text:
        return False
    if text in VEHICLE_SUPERCLASS:
        return True
    return text.lower() in _VEHICLE_HINTS


def _best_hint(box, alert_boxes) -> str | None:
    src = _bbox(box)
    if not src:
        return None
    best = None
    best_iou = 0.4
    for other in alert_boxes or []:
        if not isinstance(other, dict):
            continue
        dst = _bbox(other)
        if not dst:
            continue
        score = _iou(src, dst)
        if score > best_iou:
            best_iou = score
            best = str(other.get("label") or dst.get("label") or "").strip()
    return best or None


def _apply_alert_hints(raw, alert_boxes) -> list:
    out = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        clone = dict(item)
        hint = _best_hint(clone, alert_boxes)
        if hint and _is_vehicle_hint(hint):
            clone["label"] = hint
        out.append(clone)
    return out

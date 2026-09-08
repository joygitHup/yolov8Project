"""Review queue: edit boxes, approve into reviewed/, discard."""
from __future__ import annotations

from django.utils import timezone

from apps.cameras.models import Camera
from apps.common import storage
from apps.flywheel.dataset import (
    DATA_YAML_KEY,
    REVIEWED_IMAGES_PREFIX,
    REVIEWED_LABELS_PREFIX,
    boxes_to_yolo_txt,
    canonical_boxes,
    class_names,
    render_data_yaml,
    yolo_txt_to_boxes,
)
from apps.flywheel.models import FlywheelSample


def _iso(dt):
    if not dt:
        return None
    return dt.isoformat()


def camera_name_map(ids) -> dict[int, str]:
    if not ids:
        return {}
    return {c.id: c.name for c in Camera.objects.filter(pk__in=ids)}


def ensure_boxes(sample: FlywheelSample) -> list:
    existing = sample.boxes if isinstance(sample.boxes, list) else []
    if existing:
        return canonical_boxes(existing)
    raw = storage.get_bytes(sample.label_key) or b""
    text = raw.decode("utf-8", errors="ignore")
    boxes = yolo_txt_to_boxes(text)
    if boxes:
        sample.boxes = boxes
        sample.box_count = len(boxes)
        sample.save(update_fields=["boxes", "box_count"])
    return boxes


def sample_to_dict(sample: FlywheelSample, *, with_boxes=False, names=None, camera_names=None) -> dict:
    names = names if names is not None else class_names()
    if camera_names is not None:
        cam = camera_names.get(sample.camera_id) or ""
    else:
        row = Camera.objects.filter(pk=sample.camera_id).first()
        cam = row.name if row else ""
    data = {
        "id": sample.id,
        "cameraId": sample.camera_id,
        "cameraName": cam or f"摄像头 {sample.camera_id}",
        "source": sample.source,
        "status": sample.status,
        "alertId": sample.alert_id,
        "stem": sample.stem,
        "boxCount": sample.box_count,
        "maxConf": round(float(sample.max_conf or 0), 4),
        "reviewedBy": sample.reviewed_by or "",
        "reviewedAt": _iso(sample.reviewed_at),
        "createdAt": _iso(sample.created_at),
    }
    if with_boxes:
        data["boxes"] = ensure_boxes(sample)
        data["classNames"] = names
    return data


def write_auto_labels(sample: FlywheelSample, boxes: list) -> int:
    names = class_names()
    txt, count = boxes_to_yolo_txt(boxes, names)
    storage.put_key(sample.label_key, (txt or "").encode("utf-8") or b"\n", "text/plain")
    sample.boxes = boxes
    sample.box_count = count
    return count


def write_reviewed(sample: FlywheelSample, boxes: list) -> None:
    jpeg = storage.get_bytes(sample.image_key)
    if not jpeg:
        raise RuntimeError("样本图片不存在，无法通过")
    names = class_names()
    txt, count = boxes_to_yolo_txt(boxes, names)
    image_key = f"{REVIEWED_IMAGES_PREFIX}/{sample.stem}.jpg"
    label_key = f"{REVIEWED_LABELS_PREFIX}/{sample.stem}.txt"
    if not storage.put_key(image_key, jpeg, "image/jpeg"):
        raise RuntimeError("写入 reviewed 图片失败")
    if storage.put_key(label_key, (txt or "").encode("utf-8") or b"\n", "text/plain") is None:
        raise RuntimeError("写入 reviewed 标签失败")
    storage.put_key(DATA_YAML_KEY, render_data_yaml(names).encode("utf-8"), "text/yaml")
    sample.reviewed_image_key = image_key
    sample.reviewed_label_key = label_key
    sample.boxes = boxes
    sample.box_count = count


def save_boxes(sample: FlywheelSample, raw_boxes) -> FlywheelSample:
    if sample.status == "discarded":
        raise ValueError("已丢弃的样本不能修改")
    boxes = canonical_boxes(raw_boxes)
    write_auto_labels(sample, boxes)
    fields = ["boxes", "box_count"]
    if sample.status == "approved":
        write_reviewed(sample, boxes)
        fields.extend(["reviewed_image_key", "reviewed_label_key"])
    sample.save(update_fields=fields)
    return sample


def approve_sample(sample: FlywheelSample, raw_boxes=None, operator: str = "") -> FlywheelSample:
    boxes = canonical_boxes(raw_boxes) if raw_boxes is not None else ensure_boxes(sample)
    write_auto_labels(sample, boxes)
    write_reviewed(sample, boxes)
    sample.status = "approved"
    sample.reviewed_by = (operator or "auto")[:64]
    sample.reviewed_at = timezone.now()
    sample.save()
    return sample


def discard_sample(sample: FlywheelSample, operator: str = "") -> FlywheelSample:
    sample.status = "discarded"
    sample.reviewed_by = (operator or "")[:64]
    sample.reviewed_at = timezone.now()
    sample.save(update_fields=["status", "reviewed_by", "reviewed_at"])
    return sample


def next_pending(*, after_id: int = 0) -> FlywheelSample | None:
    qs = FlywheelSample.objects.filter(status="pending").order_by("id")
    if after_id:
        qs = qs.filter(id__gt=after_id)
    sample = qs.first()
    if sample is None and after_id:
        sample = FlywheelSample.objects.filter(status="pending").order_by("id").first()
    return sample

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
        boxes = canonical_boxes(existing)
        old_labels = [str(item.get("label") or "") for item in existing if isinstance(item, dict)]
        new_labels = [str(item.get("label") or "") for item in boxes]
        if old_labels != new_labels:
            write_auto_labels(sample, boxes)
            sample.save(update_fields=["boxes", "box_count"])
        return boxes
    raw = storage.get_bytes(sample.label_key) or b""
    text = raw.decode("utf-8", errors="ignore")
    boxes = yolo_txt_to_boxes(text)
    if boxes:
        sample.boxes = boxes
        sample.box_count = len(boxes)
        sample.save(update_fields=["boxes", "box_count"])
    return boxes


def _iou(a: dict, b: dict) -> float:
    ab = a.get("bbox") or {}
    bb = b.get("bbox") or {}
    ax, ay = float(ab.get("x") or 0), float(ab.get("y") or 0)
    aw, ah = float(ab.get("w") or 0), float(ab.get("h") or 0)
    bx, by = float(bb.get("x") or 0), float(bb.get("y") or 0)
    bw, bh = float(bb.get("w") or 0), float(bb.get("h") or 0)
    inter_w = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    inter_h = max(0.0, min(ay + ah, by + bh) - max(ay, by))
    inter = inter_w * inter_h
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def quality_score(boxes: list) -> dict:
    """
    Heuristic annotation quality (0-100). Derived from the current boxes only
    (not persisted) — used to help reviewers spot sloppy labels before they
    enter the training set.
    """
    boxes = boxes or []
    n = len(boxes)
    if n == 0:
        return {"score": 40, "issues": ["未标注任何目标（确属空场景可忽略）"], "boxCount": 0}

    score = 70.0
    issues: list[str] = []
    confs = [float(b.get("confidence") or 0) for b in boxes]
    avg_conf = sum(confs) / n
    if avg_conf >= 0.8:
        score += 15
    elif avg_conf >= 0.6:
        score += 10
    elif avg_conf >= 0.4:
        score += 5
    else:
        issues.append(f"平均置信度偏低（{avg_conf:.2f}）")

    tiny = huge = dup = 0
    for b in boxes:
        bb = b.get("bbox") or {}
        w = float(bb.get("w") or 0)
        h = float(bb.get("h") or 0)
        if w * h < 0.0005:
            tiny += 1
        if w > 0.9 and h > 0.9:
            huge += 1
    for i in range(n):
        for j in range(i + 1, n):
            if boxes[i].get("label") != boxes[j].get("label"):
                continue
            if _iou(boxes[i], boxes[j]) > 0.8:
                dup += 1

    if tiny:
        issues.append(f"{tiny} 个框面积过小（<0.05% 画面）")
        score -= min(24, 8 * tiny)
    if huge:
        issues.append(f"{huge} 个框几乎覆盖全画面")
        score -= min(20, 10 * huge)
    if dup:
        issues.append(f"{dup} 组同类框高度重叠（疑似重复标注）")
        score -= min(24, 12 * dup)
    if n > 50:
        issues.append(f"单图 {n} 个框，数量偏多")

    return {"score": int(max(0, min(100, round(score)))), "issues": issues, "boxCount": n}


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
        "classNames": names,
    }
    if with_boxes:
        boxes = ensure_boxes(sample)
        data["boxes"] = boxes
        data["quality"] = quality_score(boxes)
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

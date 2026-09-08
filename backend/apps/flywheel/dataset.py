"""YOLO txt + data.yaml helpers for the flywheel dataset."""
from __future__ import annotations

from apps.systemcfg.defaults import DEFAULT_YOLO_WEIGHTS
from apps.systemcfg.model_names import (
    model_class_names,
    resolve_to_model_name,
)

DATASET_PREFIX = "flywheel/dataset"
IMAGES_PREFIX = f"{DATASET_PREFIX}/auto/images"
LABELS_PREFIX = f"{DATASET_PREFIX}/auto/labels"
REVIEWED_IMAGES_PREFIX = f"{DATASET_PREFIX}/reviewed/images"
REVIEWED_LABELS_PREFIX = f"{DATASET_PREFIX}/reviewed/labels"
DATA_YAML_KEY = f"{DATASET_PREFIX}/data.yaml"


def class_names() -> list[str]:
    """Full names inside the current .pt. Not the enabled-checkbox subset."""
    path = DEFAULT_YOLO_WEIGHTS
    try:
        from apps.systemcfg.models import SystemSetting

        row = SystemSetting.objects.filter(key="detection").only("value").first()
        if row and isinstance(row.value, dict) and row.value.get("modelPath"):
            path = str(row.value.get("modelPath") or path)
    except Exception:
        pass
    return model_class_names(path)


def class_id_for_label(label: str, names: list[str] | None = None) -> int | None:
    """Map a raw YOLO/COCO name onto dataset class indices.

    bus/bike/moto stay distinct when those classes exist; otherwise 乱停乱放.
    Never fall through to 轿车 just because they share the parking alert type.
    """
    names = names if names is not None else class_names()
    resolved = resolve_to_model_name(label, names)
    if not resolved:
        return None
    try:
        return names.index(resolved)
    except ValueError:
        return None


def canonical_label(label: str, names: list[str] | None = None) -> str | None:
    names = names if names is not None else class_names()
    return resolve_to_model_name(label, names)


def boxes_to_yolo_txt(boxes, names: list[str] | None = None) -> tuple[str, int]:
    """Return (txt_body, kept_count). Input boxes: flat or {bbox,label,confidence}."""
    names = names if names is not None else class_names()
    lines = []
    for item in boxes or []:
        if not isinstance(item, dict):
            continue
        bbox = item.get("bbox") if isinstance(item.get("bbox"), dict) else item
        if not isinstance(bbox, dict):
            continue
        cid = class_id_for_label(item.get("label") or bbox.get("label") or "", names)
        if cid is None:
            continue
        try:
            x = float(bbox.get("x") or 0)
            y = float(bbox.get("y") or 0)
            w = float(bbox.get("w") or 0)
            h = float(bbox.get("h") or 0)
        except (TypeError, ValueError):
            continue
        if w <= 0 or h <= 0:
            continue
        cx = min(1.0, max(0.0, x + w / 2.0))
        cy = min(1.0, max(0.0, y + h / 2.0))
        w = min(1.0, max(0.0, w))
        h = min(1.0, max(0.0, h))
        lines.append(f"{cid} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
    body = ("\n".join(lines) + "\n") if lines else ""
    return body, len(lines)


def canonical_boxes(raw, names: list[str] | None = None) -> list[dict]:
    """Normalize boxes to {id,label,confidence,bbox{x,y,w,h}} using dataset class names."""
    names = names if names is not None else class_names()
    out = []
    for idx, item in enumerate(raw or []):
        if not isinstance(item, dict):
            continue
        bbox = item.get("bbox") if isinstance(item.get("bbox"), dict) else item
        if not isinstance(bbox, dict):
            continue
        label = canonical_label(item.get("label") or bbox.get("label") or "", names)
        if not label:
            continue
        try:
            x = float(bbox.get("x") or 0)
            y = float(bbox.get("y") or 0)
            w = float(bbox.get("w") or 0)
            h = float(bbox.get("h") or 0)
        except (TypeError, ValueError):
            continue
        if w <= 0 or h <= 0:
            continue
        x = min(1.0, max(0.0, x))
        y = min(1.0, max(0.0, y))
        w = min(1.0 - x, max(0.002, w))
        h = min(1.0 - y, max(0.002, h))
        try:
            conf = float(item.get("confidence", bbox.get("confidence")) or 0)
        except (TypeError, ValueError):
            conf = 0.0
        out.append({
            "id": idx + 1,
            "label": label,
            "confidence": conf,
            "bbox": {"x": x, "y": y, "w": w, "h": h},
        })
    return out


def yolo_txt_to_boxes(text: str, names: list[str] | None = None) -> list[dict]:
    names = names if names is not None else class_names()
    boxes = []
    for line in (text or "").splitlines():
        parts = line.strip().split()
        if len(parts) < 5:
            continue
        try:
            cid = int(float(parts[0]))
            cx, cy, w, h = (float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4]))
        except (TypeError, ValueError):
            continue
        if cid < 0 or cid >= len(names) or w <= 0 or h <= 0:
            continue
        boxes.append({
            "label": names[cid],
            "confidence": 1.0,
            "bbox": {
                "x": max(0.0, cx - w / 2.0),
                "y": max(0.0, cy - h / 2.0),
                "w": w,
                "h": h,
            },
        })
    return canonical_boxes(boxes, names)


def render_data_yaml(names: list[str] | None = None) -> str:
    names = names if names is not None else class_names()
    lines = [
        "# flywheel P1: train/val are human-reviewed samples only.",
        "train: reviewed/images",
        "val: reviewed/images",
        "names:",
    ]
    for i, name in enumerate(names):
        lines.append(f"  {i}: {name}")
    return "\n".join(lines) + "\n"

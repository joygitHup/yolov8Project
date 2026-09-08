"""YOLO txt + data.yaml helpers for the flywheel dataset."""
from __future__ import annotations

from apps.systemcfg.defaults import DEFAULT_LABEL_TYPE_MAP
from apps.systemcfg.services import get_section

DATASET_PREFIX = "flywheel/dataset"
IMAGES_PREFIX = f"{DATASET_PREFIX}/auto/images"
LABELS_PREFIX = f"{DATASET_PREFIX}/auto/labels"
REVIEWED_IMAGES_PREFIX = f"{DATASET_PREFIX}/reviewed/images"
REVIEWED_LABELS_PREFIX = f"{DATASET_PREFIX}/reviewed/labels"
DATA_YAML_KEY = f"{DATASET_PREFIX}/data.yaml"

# English / COCO-ish names → Chinese class names used by the trained weights.
# Do not collapse bus/bike/moto into 轿车.
LABEL_ALIASES = {
    "person": "人员",
    "car": "轿车",
    "truck": "卡车",
    "bus": "公交车",
    "bicycle": "自行车",
    "motorcycle": "摩托车",
    "bike": "自行车",
    "motorbike": "摩托车",
    "fire": "火焰",
    "smoke": "烟雾",
}


def class_names() -> list[str]:
    cats = get_section("detection").get("categories") or []
    names: list[str] = []
    seen: set[str] = set()
    for item in cats:
        text = str(item).strip()
        if text and text not in seen:
            names.append(text)
            seen.add(text)
    return names or ["火焰", "乱停乱放", "乱扔垃圾", "网格区违停"]


def _alias_for(label: str) -> str | None:
    text = str(label or "").strip()
    if not text:
        return None
    return LABEL_ALIASES.get(text) or LABEL_ALIASES.get(text.lower())


def class_id_for_label(label: str, names: list[str] | None = None) -> int | None:
    """Map a raw YOLO/COCO name onto dataset class indices.

    Distinct vehicles stay distinct: bus→公交车, bicycle→自行车, motorcycle→摩托车.
    Never fall through to 轿车 just because they share the parking alert type.
    """
    names = names if names is not None else class_names()
    text = str(label or "").strip()
    if not text:
        return None
    index = {name: i for i, name in enumerate(names)}
    lower = {name.lower(): i for i, name in enumerate(names)}
    if text in index:
        return index[text]
    if text.lower() in lower:
        return lower[text.lower()]
    alias = _alias_for(text)
    if alias:
        if alias in index:
            return index[alias]
        if alias.lower() in lower:
            return lower[alias.lower()]
        return None
    if text in LABEL_ALIASES.values():
        return None
    mapping = get_section("detection").get("labelTypeMap") or dict(DEFAULT_LABEL_TYPE_MAP)
    alert_type = mapping.get(text) or mapping.get(text.lower())
    if not alert_type:
        folded = {str(k).lower(): v for k, v in mapping.items()}
        alert_type = folded.get(text.lower())
    if not alert_type:
        return None
    for i, name in enumerate(names):
        if mapping.get(name) == alert_type:
            return i
    return None


def canonical_label(label: str, names: list[str] | None = None) -> str | None:
    names = names if names is not None else class_names()
    text = str(label or "").strip()
    if not text:
        return None
    cid = class_id_for_label(text, names)
    if cid is not None:
        return names[cid]
    return _alias_for(text)


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

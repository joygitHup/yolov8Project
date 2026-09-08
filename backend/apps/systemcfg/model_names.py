"""Read class names from the configured YOLO .pt without loading Ultralytics."""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# flywheel_2 / train-6 weights. Not the 4-class my_model-2 checkpoint.
DEFAULT_MODEL_CLASS_NAMES = [
    "火焰",
    "乱停乱放",
    "乱扔垃圾",
    "网格区违停",
    "人员",
    "轿车",
    "卡车",
    "烟雾",
    "其他",
    "危险",
    "烟雾小",
]
LEGACY_FOUR = ("火焰", "乱停乱放", "乱扔垃圾", "网格区违停")
PARKING_NAME = "乱停乱放"
VEHICLE_SUPERCLASS = ("公交车", "自行车", "摩托车")
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

_cache: dict[str, tuple[float, tuple[str, ...]]] = {}


def names_from_weights(path: Optional[str]) -> list[str]:
    text = str(path or "").strip()
    if not text or not os.path.isfile(text):
        return []
    try:
        mtime = os.path.getmtime(text)
    except OSError:
        return []
    cached = _cache.get(text)
    if cached and cached[0] == mtime:
        return list(cached[1])
    names = _read_pt_names(text)
    if names:
        _cache[text] = (mtime, tuple(names))
    return names


def model_class_names(path: Optional[str] = None) -> list[str]:
    names = names_from_weights(path)
    return names or list(DEFAULT_MODEL_CLASS_NAMES)


def resolve_to_model_name(raw, names: list[str] | None = None) -> str | None:
    """Map YOLO/COCO/English labels onto names inside the current weights.

    bus/bike/moto become 公交车/自行车/摩托车 when those classes exist;
    otherwise they fold into 乱停乱放, never 轿车.
    """
    names = list(names or DEFAULT_MODEL_CLASS_NAMES)
    text = str(raw or "").strip()
    if not text:
        return None
    if text in names:
        return text
    lower = {name.lower(): name for name in names}
    hit = lower.get(text.lower())
    if hit:
        return hit
    mapped = LABEL_ALIASES.get(text) or LABEL_ALIASES.get(text.lower())
    if mapped and mapped in names:
        return mapped
    if mapped in VEHICLE_SUPERCLASS and PARKING_NAME in names:
        return PARKING_NAME
    if text in VEHICLE_SUPERCLASS and PARKING_NAME in names:
        return PARKING_NAME
    return None


def enabled_categories(raw, model_names: list[str], *, user_set: bool = False) -> list[str]:
    """Enabled-class filter. Unchecking a class must not change YOLO indices."""
    names = list(model_names or DEFAULT_MODEL_CLASS_NAMES)
    if not user_set:
        return list(names)
    incoming = [str(item).strip() for item in (raw or []) if str(item).strip()]
    out: list[str] = []
    seen: set[str] = set()
    for item in incoming:
        resolved = resolve_to_model_name(item, names)
        if resolved and resolved not in seen:
            seen.add(resolved)
            out.append(resolved)
    return out or list(names)
    out: list[str] = []
    seen: set[str] = set()
    for item in incoming:
        resolved = resolve_to_model_name(item, names)
        if resolved and resolved not in seen:
            seen.add(resolved)
            out.append(resolved)
    return out or list(names)


def _read_pt_names(path: str) -> list[str]:
    try:
        import torch
    except Exception:
        return []
    try:
        try:
            ckpt = torch.load(path, map_location="cpu", weights_only=False)
        except TypeError:
            ckpt = torch.load(path, map_location="cpu")
    except Exception:
        logger.exception("failed to read class names from %s", path)
        return []
    raw = None
    if isinstance(ckpt, dict):
        raw = ckpt.get("names")
        if raw is None:
            train = ckpt.get("train_args") or {}
            if isinstance(train, dict):
                raw = train.get("names")
        if raw is None:
            model = ckpt.get("model")
            raw = getattr(model, "names", None)
        if raw is None:
            ema = ckpt.get("ema")
            raw = getattr(ema, "names", None)
    del ckpt
    return _normalize_names(raw)


def _normalize_names(raw) -> list[str]:
    if isinstance(raw, dict):
        try:
            keys = sorted(raw.keys(), key=lambda k: int(k))
        except Exception:
            keys = list(raw.keys())
        return [str(raw[k]).strip() for k in keys if str(raw[k]).strip()]
    if isinstance(raw, (list, tuple)):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []

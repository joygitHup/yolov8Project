import copy
from apps.systemcfg.defaults import default_settings
from apps.systemcfg.models import SystemSetting


def get_all_settings():
    data = default_settings()
    for row in SystemSetting.objects.all():
        if isinstance(data.get(row.key), dict) and isinstance(row.value, dict):
            data[row.key] = deep_merge(data[row.key], row.value)
        elif row.key:
            data[row.key] = row.value
    return normalize_settings(data)


def get_section(key):
    defaults = default_settings().get(key, {})
    row = SystemSetting.objects.filter(key=key).first()
    if not row:
        value = copy.deepcopy(defaults) if isinstance(defaults, dict) else defaults
    elif isinstance(defaults, dict) and isinstance(row.value, dict):
        value = deep_merge(defaults, row.value)
    else:
        value = row.value
    if key == "system":
        return normalize_system(value if isinstance(value, dict) else {})
    if key == "alertDeduplication":
        return normalize_dedup(value if isinstance(value, dict) else {})
    if key == "detection":
        return normalize_detection(value if isinstance(value, dict) else {})
    if key == "flywheel":
        return normalize_flywheel(value if isinstance(value, dict) else {})
    return value


def save_section(key, value):
    SystemSetting.objects.update_or_create(key=key, defaults={"value": value})
    return value


def deep_merge(base, patch):
    result = copy.deepcopy(base)
    if not isinstance(patch, dict):
        return patch
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _as_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "on"):
        return True
    if text in ("0", "false", "no", "off"):
        return False
    return default


def _as_int(value, default, low=None, high=None):
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        number = default
    if low is not None:
        number = max(low, number)
    if high is not None:
        number = min(high, number)
    return number


def _as_float(value, default, low=None, high=None):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    if low is not None:
        number = max(low, number)
    if high is not None:
        number = min(high, number)
    return number


def normalize_system(raw):
    raw = raw or {}
    title = str(raw.get("title") or "YOLOv8 视频智能分析系统").strip() or "YOLOv8 视频智能分析系统"
    return {
        "title": title,
        "logo": str(raw.get("logo") or "").strip(),
        "version": str(raw.get("version") or "1.0.0").strip() or "1.0.0",
    }


def normalize_dedup(raw):
    raw = raw or {}
    return {
        "enabled": _as_bool(raw.get("enabled"), True),
        "interval": _as_int(raw.get("interval"), 30, low=5, high=300),
    }


def normalize_detection(raw):
    from apps.systemcfg.defaults import DEFAULT_LABEL_TYPE_MAP, DEFAULT_YOLO_WEIGHTS

    raw = raw or {}
    categories = raw.get("categories") or []
    if not isinstance(categories, list):
        categories = []
    label_map = raw.get("labelTypeMap")
    if not isinstance(label_map, dict) or not label_map:
        label_map = dict(DEFAULT_LABEL_TYPE_MAP)
    else:
        cleaned = {}
        for k, v in label_map.items():
            key = str(k).strip()
            val = str(v).strip()
            if key and val in ("intrusion", "parking", "fire"):
                cleaned[key] = val
        label_map = cleaned or dict(DEFAULT_LABEL_TYPE_MAP)

    model_path = str(raw.get("modelPath") or DEFAULT_YOLO_WEIGHTS).strip() or DEFAULT_YOLO_WEIGHTS
    return {
        "confidenceThreshold": round(_as_float(raw.get("confidenceThreshold"), 0.5, 0.1, 0.95), 2),
        "iouThreshold": round(_as_float(raw.get("iouThreshold"), 0.45, 0.1, 0.9), 2),
        "fps": round(_as_float(raw.get("fps"), 2, 0.5, 10), 2),
        "maxDetections": _as_int(raw.get("maxDetections"), 100, 10, 500),
        "categories": [str(item) for item in categories],
        "trackingEnabled": _as_bool(raw.get("trackingEnabled"), True),
        "trackLostFrames": _as_int(raw.get("trackLostFrames"), 30, 1, 100),
        "modelPath": model_path,
        "inferEnabled": _as_bool(raw.get("inferEnabled"), True),
        "labelTypeMap": label_map,
    }


def normalize_flywheel(raw):
    raw = raw or {}
    low = round(_as_float(raw.get("uncertainLow"), 0.25, 0.05, 0.8), 2)
    high = round(_as_float(raw.get("uncertainHigh"), 0.55, 0.1, 0.95), 2)
    if high < low:
        low, high = high, low
    return {
        "enabled": _as_bool(raw.get("enabled"), True),
        "alertFrames": _as_bool(raw.get("alertFrames"), True),
        "uncertainFrames": _as_bool(raw.get("uncertainFrames"), True),
        "uncertainLow": low,
        "uncertainHigh": high,
        "quotaPerCameraHour": _as_int(raw.get("quotaPerCameraHour"), 40, low=1, high=500),
        "sampleIntervalSec": _as_int(raw.get("sampleIntervalSec"), 15, low=3, high=300),
        "autoLabelMin": round(_as_float(raw.get("autoLabelMin"), 0.7, 0.4, 0.99), 2),
        "autoApproveAlerts": _as_bool(raw.get("autoApproveAlerts"), False),
        "trainRoot": (
            str(raw.get("trainRoot") or "").strip()
            or r"D:\pythonDev\industrial_anomaly_detection\yolov8modle"
        ),
        "epochs": _as_int(raw.get("epochs"), 15, low=1, high=200),
        "batch": _as_int(raw.get("batch"), 4, low=1, high=64),
        "imgsz": _as_int(raw.get("imgsz"), 640, low=320, high=1280),
        "minReviewed": _as_int(raw.get("minReviewed"), 5, low=1, high=500),
        "maxMapDrop": round(_as_float(raw.get("maxMapDrop"), 0.01, 0.0, 0.2), 3),
        "trainDevice": str(raw.get("trainDevice") or "cpu").strip() or "cpu",
    }


def normalize_settings(data=None):
    """
    Canonical settings payload (camelCase sections):
      system: { title, logo, version }
      alertDeduplication: { enabled, interval }  # interval seconds
      detection: { confidenceThreshold, iouThreshold, fps, ... }
      flywheel: { enabled, alertFrames, uncertainFrames, uncertainLow, uncertainHigh, quotaPerCameraHour, sampleIntervalSec }
      notification: { ... }
    """
    base = default_settings()
    data = data or {}
    return {
        "system": normalize_system(deep_merge(base["system"], data.get("system") or {})),
        "alertDeduplication": normalize_dedup(
            deep_merge(base["alertDeduplication"], data.get("alertDeduplication") or {})
        ),
        "detection": normalize_detection(deep_merge(base["detection"], data.get("detection") or {})),
        "flywheel": normalize_flywheel(deep_merge(base["flywheel"], data.get("flywheel") or {})),
        "notification": deep_merge(base["notification"], data.get("notification") or {}),
    }


def apply_settings_patch(patch):
    """
    Merge and validate a partial settings update.
    Returns normalized full settings after save.
    Raises ValueError on invalid input.
    """
    if not isinstance(patch, dict):
        raise ValueError("请求体必须为对象")

    current = get_all_settings()
    allowed = ("system", "alertDeduplication", "detection", "flywheel", "notification")
    touched = False

    for key in allowed:
        if key not in patch:
            continue
        section = patch.get(key)
        if not isinstance(section, dict):
            raise ValueError(f"{key} 必须为对象")
        touched = True
        merged = deep_merge(current.get(key, {}), section)
        if key == "system":
            merged = normalize_system(merged)
            if not merged["title"]:
                raise ValueError("系统标题不能为空")
        elif key == "alertDeduplication":
            merged = normalize_dedup(merged)
        elif key == "detection":
            merged = normalize_detection(merged)
        elif key == "flywheel":
            merged = normalize_flywheel(merged)
        save_section(key, merged)

    if not touched:
        raise ValueError("未提供可更新字段，可选：system / alertDeduplication / detection / flywheel / notification")

    return get_all_settings()

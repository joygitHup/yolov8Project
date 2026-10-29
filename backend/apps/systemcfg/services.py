import copy
import time

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


_SECTION_CACHE = {}
_SECTION_CACHE_AT = {}
_SECTION_TTL = 5.0  # seconds; save_section() invalidates the local cache


def get_section(key):
    now = time.monotonic()
    hit = _SECTION_CACHE_AT.get(key)
    if hit is not None and now - hit < _SECTION_TTL and key in _SECTION_CACHE:
        return copy.deepcopy(_SECTION_CACHE[key])
    value = _compute_section(key)
    _SECTION_CACHE[key] = value
    _SECTION_CACHE_AT[key] = now
    # deep-copy out so callers can mutate freely without poisoning the cache
    return copy.deepcopy(value)


def _compute_section(key):
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
    _SECTION_CACHE.pop(key, None)
    _SECTION_CACHE_AT.pop(key, None)
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


def normalize_detection(raw, *, user_set=None):
    from apps.systemcfg.defaults import DEFAULT_LABEL_TYPE_MAP, DEFAULT_YOLO_WEIGHTS
    from apps.systemcfg.model_names import enabled_categories, model_class_names

    raw = raw or {}
    categories = raw.get("categories") or []
    if not isinstance(categories, list):
        categories = []
    label_map = dict(DEFAULT_LABEL_TYPE_MAP)
    raw_map = raw.get("labelTypeMap")
    if isinstance(raw_map, dict) and raw_map:
        for k, v in raw_map.items():
            key = str(k).strip()
            val = str(v).strip()
            if key and val in ("intrusion", "parking", "fire"):
                label_map[key] = val

    model_path = str(raw.get("modelPath") or DEFAULT_YOLO_WEIGHTS).strip() or DEFAULT_YOLO_WEIGHTS
    if user_set is None:
        user_set = _as_bool(raw.get("categoriesUserSet"), False)
    model_names = model_class_names(model_path)
    return {
        "confidenceThreshold": round(_as_float(raw.get("confidenceThreshold"), 0.5, 0.1, 0.95), 2),
        "iouThreshold": round(_as_float(raw.get("iouThreshold"), 0.45, 0.1, 0.9), 2),
        "fps": round(_as_float(raw.get("fps"), 2, 0.5, 10), 2),
        "maxDetections": _as_int(raw.get("maxDetections"), 100, 10, 500),
        "categories": enabled_categories(categories, model_names, user_set=user_set),
        "categoriesUserSet": bool(user_set),
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


def _clean_list(value) -> list:
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        if item is None:
            continue
        text = str(item).strip()
        if text:
            out.append(text)
    return out


def _clean_int_list(value) -> list:
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            continue
    return out


def normalize_whitelist(raw):
    """Validate and sanitize whitelist section.

    Each rule must have:
      - id (generated if missing)
      - name
      - enabled
      - alertTypes / labels / trackIds / faceIds / cameras (all optional list filters)
      - maxConfidence (optional float cap — only suppress when det confidence <= cap)
    faceUnclearPolicy: "alert" (default, fire alert even if face match uncertain) | "review" (create review-status alert) | "suppress"
    """
    import uuid as _uuid

    raw = raw or {}
    face_policy = str(raw.get("faceUnclearPolicy") or "alert").strip()
    if face_policy not in ("alert", "review", "suppress"):
        face_policy = "alert"
    rules = []
    seen_ids = set()
    for item in raw.get("rules") or []:
        if not isinstance(item, dict):
            continue
        rid = str(item.get("id") or "").strip() or _uuid.uuid4().hex[:12]
        while rid in seen_ids:
            rid = _uuid.uuid4().hex[:12]
        seen_ids.add(rid)
        max_conf = item.get("maxConfidence")
        if max_conf is None or max_conf == "":
            max_conf_val = None
        else:
            try:
                max_conf_val = round(_as_float(max_conf, None, low=0.05, high=0.99), 2)
            except Exception:
                max_conf_val = None
        rules.append({
            "id": rid,
            "name": str(item.get("name") or "").strip() or "未命名规则",
            "enabled": _as_bool(item.get("enabled"), True),
            "alertTypes": _clean_list(item.get("alertTypes")),
            "labels": _clean_list(item.get("labels")),
            "trackIds": _clean_list(item.get("trackIds")),
            "faceIds": _clean_list(item.get("faceIds")),
            "cameras": _clean_int_list(item.get("cameras")),
            "maxConfidence": max_conf_val,
        })
    return {
        "enabled": _as_bool(raw.get("enabled"), True),
        "faceUnclearPolicy": face_policy,
        "rules": rules,
    }


def whitelist_match(camera_id: int, alert_type: str, det: dict, cfg=None) -> str:
    """Decide whether a single detection box is whitelisted.

    Returns:
      "suppress" — box is explicitly whitelisted by label / trackId / faceId / camera → skip alert
      "review"   — face unclear + cfg.faceUnclearPolicy=="review" → raise a review-status alert
      None       — not whitelisted, fire alert normally

    The caller in pipeline._maybe_alert groups boxes by alert_type; after filtering
    via this function it either creates an Alert (possibly with status="review")
    or short-circuits.
    """
    import logging

    cfg = cfg or get_section("whitelist")
    if not cfg.get("enabled", True):
        return None
    labels = cfg.get("rules") or []
    label = str(det.get("label") or "").strip()
    conf = float(det.get("confidence") or 0)
    track_id = str(det.get("trackId") or "").strip()
    face_id = str(det.get("faceId") or "").strip()
    face_clear = det.get("faceClear")  # True / False / None (no face match attempt)

    # Unclear face → apply faceUnclearPolicy BEFORE rule scan. If policy is "alert"
    # (default), fall through to normal rule matching so we can still suppress on
    # label alone; if "review", this single box becomes "review".
    if face_clear is False:
        policy = str(cfg.get("faceUnclearPolicy") or "alert").strip()
        if policy == "suppress":
            return "suppress"
        if policy == "review":
            return "review"
        # policy == "alert": fall through

    for rule in labels:
        if not rule.get("enabled", True):
            continue
        types = rule.get("alertTypes") or []
        if types and alert_type not in types:
            continue
        labs = rule.get("labels") or []
        if labs and label not in labs:
            continue
        tids = rule.get("trackIds") or []
        if tids and track_id not in tids:
            continue
        fids = rule.get("faceIds") or []
        if fids and face_id not in fids:
            continue
        cams = rule.get("cameras") or []
        if cams and camera_id not in cams:
            continue
        max_c = rule.get("maxConfidence")
        if max_c is not None and conf > float(max_c):
            continue
        # All rule filters matched → suppress
        logging.getLogger("systemcfg").info(
            "whitelist hit rule=%s camera=%s type=%s label=%s trackId=%s faceId=%s",
            rule.get("name"), camera_id, alert_type, label, track_id, face_id,
        )
        return "suppress"
    return None


def normalize_settings(data=None):
    """
    Canonical settings payload (camelCase sections):
      system: { title, logo, version }
      alertDeduplication: { enabled, interval }  # interval seconds
      detection: { confidenceThreshold, iouThreshold, fps, ... }
      whitelist: { enabled, faceUnclearPolicy, rules[] }
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
        "whitelist": normalize_whitelist(deep_merge(base["whitelist"], data.get("whitelist") or {})),
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
    allowed = ("system", "alertDeduplication", "detection", "whitelist", "flywheel", "notification")
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
            merged = normalize_detection(merged, user_set=True)
        elif key == "whitelist":
            merged = normalize_whitelist(merged)
        elif key == "flywheel":
            merged = normalize_flywheel(merged)
        save_section(key, merged)

    if not touched:
        raise ValueError("未提供可更新字段，可选：system / alertDeduplication / detection / whitelist / flywheel / notification")

    return get_all_settings()

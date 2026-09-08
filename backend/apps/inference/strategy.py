from datetime import datetime
import time

from apps.systemcfg.models import Strategy

_strategy_cache = {"at": 0.0, "items": []}
_STRATEGY_TTL = 3.0


def _enabled_strategies():
    now = time.time()
    if now - _strategy_cache["at"] < _STRATEGY_TTL and _strategy_cache["items"] is not None:
        return _strategy_cache["items"]
    items = list(Strategy.objects.filter(enabled=True))
    _strategy_cache["at"] = now
    _strategy_cache["items"] = items
    return items


def _minutes_now():
    now = datetime.now()
    return now.hour * 60 + now.minute


def _parse_hm(value, fallback):
    text = value or fallback
    hour, minute = str(text).split(":")[:2]
    return int(hour) * 60 + int(minute)


def _in_window(start, end, now):
    if start <= end:
        return start <= now <= end
    return now >= start or now <= end


def match_schedule(schedule):
    if not schedule or schedule.get("type") == "always":
        return True
    now = _minutes_now()
    kind = schedule.get("type")
    if kind == "worktime":
        return _in_window(_parse_hm(schedule.get("start"), "08:00"), _parse_hm(schedule.get("end"), "20:00"), now)
    if kind == "night":
        return _in_window(_parse_hm(schedule.get("start"), "22:00"), _parse_hm(schedule.get("end"), "06:00"), now)
    if kind == "custom":
        return _in_window(_parse_hm(schedule.get("start"), "00:00"), _parse_hm(schedule.get("end"), "23:59"), now)
    return True


def _camera_ids(strategy):
    ids = []
    for cid in strategy.camera_ids or []:
        try:
            ids.append(int(cid))
        except (TypeError, ValueError):
            continue
    return ids


def active_strategies_for_camera(camera):
    """Enabled strategies that cover this camera and pass schedule."""
    matched = []
    for strategy in _enabled_strategies():
        if camera.id not in _camera_ids(strategy):
            continue
        if not match_schedule(strategy.schedule or {}):
            continue
        matched.append(strategy)
    return matched


def should_infer(camera):
    """True when at least one active strategy covers the camera."""
    return bool(active_strategies_for_camera(camera))


def allowed_alert_types(camera):
    """
    Union of detection_types from active strategies, intersected with
    camera.detection_types when the camera list is non-empty.
    """
    strategies = active_strategies_for_camera(camera)
    if not strategies:
        return set()
    allowed = set()
    for strategy in strategies:
        for item in strategy.detection_types or []:
            key = str(item).strip()
            if key:
                allowed.add(key)
    cam_types = {str(t).strip() for t in (camera.detection_types or []) if str(t).strip()}
    if cam_types:
        allowed &= cam_types
    return allowed


def match_strategy(camera, alert_type):
    for strategy in _enabled_strategies():
        if camera.id not in _camera_ids(strategy):
            continue
        if alert_type not in (strategy.detection_types or []):
            continue
        if not match_schedule(strategy.schedule or {}):
            continue
        return strategy
    return None

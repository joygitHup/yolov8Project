from datetime import datetime

from apps.systemcfg.models import Strategy


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


def match_strategy(camera, alert_type):
    for strategy in Strategy.objects.filter(enabled=True):
        ids = []
        for cid in strategy.camera_ids or []:
            try:
                ids.append(int(cid))
            except (TypeError, ValueError):
                continue
        if camera.id not in ids:
            continue
        if alert_type not in (strategy.detection_types or []):
            continue
        if not match_schedule(strategy.schedule or {}):
            continue
        return strategy
    return None

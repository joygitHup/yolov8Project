from datetime import datetime, timezone as dt_timezone

_FRAMES = {}


def set_frame(camera_id, frame):
    _FRAMES[int(camera_id)] = frame


def get_latest_frame(camera_id):
    return _FRAMES.get(int(camera_id))


def get_all_frames():
    return _FRAMES

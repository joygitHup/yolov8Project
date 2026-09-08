from apps.common import rdb

_FRAMES = {}


def set_frame(camera_id, frame):
    cid = int(camera_id)
    _FRAMES[cid] = frame
    try:
        rdb.put_last_frame_meta(cid, frame or {})
    except Exception:
        pass


def get_latest_frame(camera_id):
    cid = int(camera_id)
    local = _FRAMES.get(cid)
    if local:
        return local
    try:
        return rdb.get_last_frame_meta(cid)
    except Exception:
        return None


def get_all_frames():
    return _FRAMES

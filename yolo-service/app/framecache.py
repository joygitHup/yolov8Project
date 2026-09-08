"""Push the inferred JPEG into Redis so Django can snapshot the same frame."""
from __future__ import annotations

import logging
import os
import threading

logger = logging.getLogger("yolo.framecache")

_PREFIX = (os.environ.get("REDIS_PREFIX") or "yolov8").strip() or "yolov8"
_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/2")
_TTL = max(2, int(os.environ.get("YOLO_FRAME_TTL", "30") or 30))
_QUALITY = 92

_client = None
_failed = False
_lock = threading.Lock()


def _redis():
    global _client, _failed
    if _client is not None:
        return _client
    if _failed:
        return None
    with _lock:
        if _client is not None or _failed:
            return _client
        try:
            import redis as redis_lib

            client = redis_lib.Redis.from_url(
                _URL,
                decode_responses=False,
                socket_connect_timeout=1,
                socket_timeout=2,
            )
            client.ping()
            _client = client
            logger.info("frame cache redis %s", _URL)
            return _client
        except Exception as exc:
            _failed = True
            logger.warning("frame cache redis unavailable: %s", exc)
            return None


def put_jpeg(camera_id: int, jpeg: bytes) -> None:
    if not jpeg:
        return
    client = _redis()
    if client is None:
        return
    try:
        client.setex(f"{_PREFIX}:frame:{int(camera_id)}", _TTL, jpeg)
        key = f"{_PREFIX}:clip:ring:{int(camera_id)}"
        pipe = client.pipeline()
        pipe.lpush(key, jpeg)
        pipe.ltrim(key, 0, 23)
        pipe.expire(key, 180)
        pipe.execute()
    except Exception as exc:
        logger.debug("frame cache write failed camera=%s: %s", camera_id, exc)


def put_frame(camera_id: int, frame_bgr) -> None:
    if frame_bgr is None:
        return
    try:
        import cv2

        ok, buf = cv2.imencode(".jpg", frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), _QUALITY])
        if not ok:
            return
        put_jpeg(camera_id, buf.tobytes())
    except Exception as exc:
        logger.debug("frame cache encode failed camera=%s: %s", camera_id, exc)

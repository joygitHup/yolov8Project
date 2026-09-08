"""Shared OpenCV frame grabbers keyed by RTSP URL (many cameras may share one stream)."""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger("inference.frames")

_lock = threading.Lock()
_grab_sem = threading.Semaphore(1)  # serialize OpenCV reads — avoid starving API threads
_captures: dict[str, Any] = {}  # url -> VideoCapture
_url_by_camera: dict[int, str] = {}
_last_error: dict[int, str] = {}
_last_ok: dict[int, float] = {}
_last_frame: dict[str, Any] = {}  # url -> (timestamp, frame)
_FRAME_CACHE_SEC = 0.4


def get_last_error(camera_id: int) -> str | None:
    return _last_error.get(int(camera_id))


def _open_capture(rtsp: str):
    import cv2

    url = (rtsp or "").strip()
    if not url:
        return None
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        try:
            cap.release()
        except Exception:
            pass
        cap = cv2.VideoCapture(url)
    if not cap.isOpened():
        try:
            cap.release()
        except Exception:
            pass
        return None
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass
    return cap


def release_camera(camera_id: int) -> None:
    cid = int(camera_id)
    with _lock:
        url = _url_by_camera.pop(cid, None)
        _last_error.pop(cid, None)
        _last_ok.pop(cid, None)
        if not url:
            return
        # Keep shared URL capture if other cameras still use it
        if url in _url_by_camera.values():
            return
        cap = _captures.pop(url, None)
        _last_frame.pop(url, None)
    if cap is not None:
        try:
            cap.release()
        except Exception:
            pass


def release_all() -> None:
    with _lock:
        caps = list(_captures.values())
        _captures.clear()
        _url_by_camera.clear()
        _last_error.clear()
        _last_ok.clear()
        _last_frame.clear()
    for cap in caps:
        try:
            cap.release()
        except Exception:
            pass


def grab_frame(camera_id: int, rtsp: str, *, reopen_after_sec: float = 30.0):
    """
    Grab one BGR frame. Captures are shared by identical RTSP URLs.
    Returns numpy ndarray or None.
    """
    cid = int(camera_id)
    url = (rtsp or "").strip()
    if not url:
        _last_error[cid] = "empty rtsp"
        return None

    # Reuse very recent frame for same URL (multi-camera sharing one publish)
    now = time.time()
    with _lock:
        cached = _last_frame.get(url)
        if cached and now - cached[0] <= _FRAME_CACHE_SEC:
            _url_by_camera[cid] = url
            _last_ok[cid] = now
            _last_error.pop(cid, None)
            return cached[1]

    if not _grab_sem.acquire(timeout=1.5):
        _last_error[cid] = "grab busy"
        return None
    try:
        with _lock:
            _url_by_camera[cid] = url
            cap = _captures.get(url)

        if cap is None:
            cap = _open_capture(url)
            if cap is None:
                _last_error[cid] = f"cannot open: {url}"
                logger.warning("Frame source open failed camera=%s url=%s", cid, url)
                return None
            with _lock:
                _captures[url] = cap

        ok, frame = False, None
        try:
            cap.grab()
            ok, frame = cap.read()
        except Exception as exc:
            _last_error[cid] = str(exc)
            logger.warning("Frame read error camera=%s: %s", cid, exc)
            ok, frame = False, None

        if not ok or frame is None:
            with _lock:
                old = _captures.pop(url, None)
                _last_frame.pop(url, None)
            if old is not None:
                try:
                    old.release()
                except Exception:
                    pass
            time.sleep(0.05)
            cap = _open_capture(url)
            if cap is None:
                _last_error[cid] = f"reconnect failed: {url}"
                return None
            with _lock:
                _captures[url] = cap
            try:
                ok, frame = cap.read()
            except Exception as exc:
                _last_error[cid] = str(exc)
                return None
            if not ok or frame is None:
                _last_error[cid] = "empty frame"
                return None

        with _lock:
            _last_frame[url] = (time.time(), frame)
        _last_error.pop(cid, None)
        _last_ok[cid] = time.time()
        return frame
    finally:
        _grab_sem.release()

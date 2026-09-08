"""Shared OpenCV grabbers keyed by RTSP URL."""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

# Must be set before cv2 is imported: TCP + discard corrupt packets.
# BUFFERSIZE=1 and grab()+read() (dropping the last keyframe) cause mosaic/tear frames.
os.environ.setdefault(
    "OPENCV_FFMPEG_CAPTURE_OPTIONS",
    "rtsp_transport;tcp|fflags;nobuffer+discardcorrupt",
)

logger = logging.getLogger("yolo.frames")

_lock = threading.Lock()
_grab_sem = threading.Semaphore(2)
_captures: dict[str, Any] = {}
_url_by_camera: dict[int, str] = {}
_last_error: dict[int, str] = {}
_last_frame: dict[str, Any] = {}
_FRAME_CACHE_SEC = 0.35


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
    # Warm up until a keyframe can be decoded; do not drop frames with grab().
    for _ in range(8):
        cap.read()
    return cap


def release_camera(camera_id: int) -> None:
    cid = int(camera_id)
    with _lock:
        url = _url_by_camera.pop(cid, None)
        _last_error.pop(cid, None)
        if not url:
            return
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
        _last_frame.clear()
    for cap in caps:
        try:
            cap.release()
        except Exception:
            pass


def grab_frame(camera_id: int, rtsp: str):
    cid = int(camera_id)
    url = (rtsp or "").strip()
    if not url:
        _last_error[cid] = "empty rtsp"
        return None

    now = time.time()
    with _lock:
        cached = _last_frame.get(url)
        if cached and now - cached[0] <= _FRAME_CACHE_SEC:
            _url_by_camera[cid] = url
            _last_error.pop(cid, None)
            return cached[1]

    if not _grab_sem.acquire(timeout=2.0):
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
                return None
            with _lock:
                _captures[url] = cap

        ok, frame = False, None
        try:
            ok, frame = cap.read()
        except Exception as extra:
            _last_error[cid] = str(extra)
            ok, frame = False, None
        if ok and frame is not None:
            try:
                import numpy as np

                if not frame.flags["C_CONTIGUOUS"]:
                    frame = np.ascontiguousarray(frame)
            except Exception:
                pass

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
                _last_error[cid] = "reconnect failed"
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
        return frame
    finally:
        _grab_sem.release()


def last_error(camera_id: int) -> str | None:
    return _last_error.get(int(camera_id))

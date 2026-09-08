"""Grab a full-resolution JPEG from live RTSP for flywheel sampling."""
from __future__ import annotations

import logging

logger = logging.getLogger("flywheel.capture")


def grab_rtsp_jpeg(rtsp: str, quality: int = 95, camera_id: int | None = None) -> bytes | None:
    """Publisher-side keyframe JPEG (ffmpeg I-frame), never OpenCV P-frames."""
    del quality  # ffmpeg -q:v 2
    from apps.streaming.grab import grab_camera_keyframe, grab_keyframe_jpeg

    data = grab_camera_keyframe(camera_id, rtsp or "")
    if data:
        return data
    url = (rtsp or "").strip()
    if url:
        data = grab_keyframe_jpeg(url)
        if data:
            return data
    logger.warning("rtsp grab failed: %s", url)
    return None

"""Grab a clean JPEG keyframe from the published RTSP (not OpenCV P-frames)."""
from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger("streaming.grab")


def publisher_rtsp(camera_id: int | None, camera_rtsp: str = "") -> str:
    """MediaMTX RTSP for this camera's preview path (same stream as HLS)."""
    from apps.streaming import mediamtx as mtx

    return mtx.published_rtsp(camera_rtsp or "", camera_id)


def grab_keyframe_jpeg(rtsp: str) -> bytes | None:
    """ffmpeg `-skip_frame nokey` so the JPEG is an I-frame, not a mosaic P-frame."""
    from apps.streaming.ffmpeg import find_ffmpeg, popen_kwargs

    url = (rtsp or "").strip()
    ffmpeg = find_ffmpeg()
    if not ffmpeg or not url:
        return None
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        out = Path(tmp.name)
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel", "error",
        "-rtsp_transport", "tcp",
        "-fflags", "+discardcorrupt+nobuffer",
        "-flags", "low_delay",
        "-skip_frame", "nokey",
        "-i", url,
        "-an",
        "-frames:v", "1",
        "-q:v", "2",
        "-y",
        str(out),
    ]
    try:
        proc = subprocess.run(cmd, timeout=25, **popen_kwargs())
        if proc.returncode == 0 and out.is_file() and out.stat().st_size > 2000:
            return out.read_bytes()
        return None
    except Exception as exc:
        logger.warning("keyframe grab failed: %s", exc)
        return None
    finally:
        try:
            out.unlink(missing_ok=True)
        except Exception:
            pass


def grab_camera_keyframe(camera_id: int | None, camera_rtsp: str = "") -> bytes | None:
    """Prefer the published MTX stream, then the camera's own RTSP."""
    seen: set[str] = set()
    for url in (publisher_rtsp(camera_id, camera_rtsp), (camera_rtsp or "").strip()):
        if not url or url in seen:
            continue
        seen.add(url)
        data = grab_keyframe_jpeg(url)
        if data:
            return data
    return None

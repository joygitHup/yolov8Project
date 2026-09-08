"""Capture real alert evidence: annotated JPEG + short RTSP MP4 clip."""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path

from apps.common import storage

logger = logging.getLogger("alerts.evidence")

_CLIP_SECONDS = 8
_LABEL_COLOR = {
    "person": (82, 196, 26),
    "car": (246, 130, 59),
    "truck": (139, 92, 246),
    "fire": (45, 34, 245),
    "smoke": (11, 158, 245),
    "火焰": (45, 34, 245),
    "乱停乱放": (246, 130, 59),
    "网格区违停": (246, 130, 59),
    "乱扔垃圾": (82, 196, 26),
}


def alerts_media_root():
    return storage.alerts_media_root()


def alert_dir(alert_id: int):
    return storage.alert_dir(alert_id)


def media_url(alert_id: int, filename: str) -> str:
    return storage.media_url(alert_id, filename)


def resolve_media_file(alert_id: int, filename: str):
    return storage.resolve_local_file(alert_id, filename)


def _bgr_color(label: str):
    rgb = _LABEL_COLOR.get(str(label), (82, 196, 26))
    return (rgb[2], rgb[1], rgb[0])


def _draw_boxes(frame, boxes):
    import cv2

    h, w = frame.shape[:2]
    for box in boxes or []:
        bbox = box.get("bbox") if isinstance(box.get("bbox"), dict) else box
        if not isinstance(bbox, dict):
            continue
        x = float(bbox.get("x") or 0) * w
        y = float(bbox.get("y") or 0) * h
        bw = float(bbox.get("w") or 0) * w
        bh = float(bbox.get("h") or 0) * h
        x1, y1 = int(max(0, x)), int(max(0, y))
        x2, y2 = int(min(w - 1, x + bw)), int(min(h - 1, y + bh))
        label = str(box.get("label") or "object")
        try:
            conf = float(box.get("confidence") or 0)
        except (TypeError, ValueError):
            conf = 0.0
        pct = conf * 100 if conf <= 1 else conf
        color = _bgr_color(label)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        text = f"{label} {pct:.0f}%"
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
        ty = max(0, y1 - th - 8)
        cv2.rectangle(frame, (x1, ty), (x1 + tw + 8, ty + th + 8), color, -1)
        cv2.putText(
            frame,
            text,
            (x1 + 4, ty + th + 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
    return frame


def _grab_frame_opencv(rtsp: str):
    import cv2

    url = (rtsp or "").strip()
    if not url:
        return None
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        cap.release()
        cap = cv2.VideoCapture(url)
    if not cap.isOpened():
        return None
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass
    ok, frame = False, None
    for _ in range(3):
        ok, frame = cap.read()
        if ok and frame is not None:
            break
    cap.release()
    return frame if ok else None


def _grab_frame_ffmpeg(rtsp: str, out_path: Path) -> bool:
    from apps.streaming.ffmpeg import find_ffmpeg, popen_kwargs

    ffmpeg = find_ffmpeg()
    if not ffmpeg or not (rtsp or "").strip():
        return False
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel", "error",
        "-rtsp_transport", "tcp",
        "-fflags", "+discardcorrupt+nobuffer",
        "-flags", "low_delay",
        "-skip_frame", "nokey",
        "-i", rtsp,
        "-an",
        "-frames:v", "1",
        "-q:v", "2",
        "-y",
        str(out_path),
    ]
    try:
        proc = subprocess.run(cmd, timeout=25, **popen_kwargs())
        return proc.returncode == 0 and out_path.is_file() and out_path.stat().st_size > 2000
    except Exception as exc:
        logger.warning("ffmpeg snapshot failed: %s", exc)
        return False


def _encode_jpeg(frame, quality: int = 95) -> bytes | None:
    import cv2

    if frame is None:
        return None
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:
        return None
    return buf.tobytes()


def capture_snapshot(alert_id: int, rtsp: str, boxes, camera_id: int | None = None, jpeg: bytes | None = None) -> str | None:
    """Store a clean publisher keyframe JPEG (boxes are drawn in the UI)."""
    del boxes  # drawn on the frontend
    from apps.streaming.grab import grab_camera_keyframe

    data = grab_camera_keyframe(camera_id, rtsp or "")
    if not data:
        data = jpeg if jpeg else None
    if not data:
        logger.warning("alert=%s snapshot grab failed rtsp=%s", alert_id, rtsp)
        return None
    return storage.put_bytes(alert_id, "snapshot.jpg", data, "image/jpeg")


def capture_clip(alert_id: int, rtsp: str, seconds: int = _CLIP_SECONDS, camera_id: int | None = None) -> str | None:
    """Concat runtime GOP preroll from the published MTX stream, then live pull."""
    from apps.streaming import preroll
    from apps.streaming.ffmpeg import find_ffmpeg, popen_kwargs
    from apps.streaming.grab import publisher_rtsp
    from apps.streaming import mediamtx as mtx

    path = ""
    if camera_id:
        path = mtx.path_from_rtsp(rtsp or "", int(camera_id))
        blob = preroll.concat_mp4(path) if path else None
        if blob:
            return storage.put_bytes(alert_id, "clip.mp4", blob, "video/mp4")

    ffmpeg = find_ffmpeg()
    camera_url = (rtsp or "").strip()
    urls = []
    pub = publisher_rtsp(camera_id, camera_url)
    for url in (pub, camera_url):
        if url and url not in urls:
            urls.append(url)
    if not ffmpeg or not urls:
        return None
    duration = max(3, min(int(seconds or _CLIP_SECONDS), 30))
    fd, tmp_name = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        for url in urls:
            for extra in (
                ["-c:v", "copy"],
                ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"],
            ):
                try:
                    if tmp.exists():
                        tmp.unlink()
                except Exception:
                    pass
                cmd = [
                    ffmpeg, "-hide_banner", "-loglevel", "error",
                    "-rtsp_transport", "tcp", "-i", url,
                    "-t", str(duration), "-an",
                    *extra,
                    "-movflags", "+faststart", "-y", str(tmp),
                ]
                try:
                    proc = subprocess.run(cmd, timeout=duration + 25, **popen_kwargs())
                    if proc.returncode == 0 and tmp.is_file() and tmp.stat().st_size > 1024:
                        return storage.put_file(alert_id, "clip.mp4", tmp, "video/mp4")
                except Exception as exc:
                    logger.warning("alert=%s clip attempt failed url=%s: %s", alert_id, url, exc)
        logger.warning("alert=%s clip capture failed urls=%s", alert_id, urls)
        return None
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass


def attach_evidence_async(alert_id: int, rtsp: str, boxes, camera_id: int | None = None) -> None:
    """Enqueue snapshot + clip (kept for callers that used the old thread helper)."""
    from apps.alerts.jobs import enqueue_evidence

    enqueue_evidence(alert_id, rtsp, boxes, camera_id=camera_id)


def enqueue_evidence(alert_id: int, rtsp: str, boxes=None, camera_id: int | None = None) -> None:
    from apps.alerts.jobs import enqueue_evidence as _enqueue

    _enqueue(alert_id, rtsp, boxes or [], camera_id=camera_id)


def reconcile_media_urls(alert) -> bool:
    """If snapshot/clip already in MinIO or local disk, ensure DB URLs point to them."""
    aid = int(alert.id)
    changed = []
    if storage.exists(aid, "snapshot.jpg"):
        url = media_url(aid, "snapshot.jpg")
        if (alert.snapshot_url or "").strip() != url:
            alert.snapshot_url = url
            alert.image_url = url
            changed.extend(["snapshot_url", "image_url"])
    if storage.exists(aid, "clip.mp4"):
        url = media_url(aid, "clip.mp4")
        if (alert.video_url or "").strip() != url:
            alert.video_url = url
            changed.append("video_url")
    if changed:
        alert.save(update_fields=list(dict.fromkeys(changed)))
        return True
    return False


def media_status(alert) -> dict:
    aid = int(alert.id)
    snap_ok = (alert.snapshot_url or "").startswith("/media/alerts/") or storage.exists(aid, "snapshot.jpg")
    vid_ok = (alert.video_url or "").startswith("/media/alerts/") or storage.exists(aid, "clip.mp4")
    return {
        "snapshotReady": bool(snap_ok),
        "videoReady": bool(vid_ok),
        "pending": not (snap_ok and vid_ok),
        "message": (
            "现场取证已就绪"
            if snap_ok and vid_ok
            else ("现场取证采集中…" if not snap_ok else "视频片段采集中…")
        ),
    }

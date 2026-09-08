"""Ensure local demo MP4 is published to MediaMTX as rtsp://127.0.0.1:8554/mystream."""
import atexit
import logging
import os
import socket
import subprocess
import threading
import time

from apps.streaming.ffmpeg import demo_video_path, find_ffmpeg, popen_kwargs

logger = logging.getLogger("streaming")

DEMO_RTSP_URL = "rtsp://127.0.0.1:8554/mystream"
DEMO_RTSP_PORT = 8554
DEMO_RTSP_PATH = "mystream"


def demo_publish_enabled() -> bool:
    """
    Auto-publish local MP4 to mystream.
    Set DEMO_RTSP_PUBLISH=0 when you push manually with ffmpeg
    (otherwise the demo publisher steals /mystream -> Broken pipe).
    Default is off so manual push works.
    """
    raw = os.environ.get("DEMO_RTSP_PUBLISH", "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


def rtsp_port_open(host="127.0.0.1", port=DEMO_RTSP_PORT, timeout=0.5):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


class DemoPublisher:
    """Loop-publish local MP4 to MediaMTX so cameras can pull a real RTSP URL."""

    def __init__(self):
        self._proc = None
        self._lock = threading.Lock()
        self._stop = False
        self._watch_thread = None

    @property
    def running(self):
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def ensure_started(self):
        if not demo_publish_enabled():
            logger.info("demo publisher disabled (DEMO_RTSP_PUBLISH=0); use manual ffmpeg push")
            self.stop()
            return False
        ffmpeg = find_ffmpeg()
        video = demo_video_path()
        if not ffmpeg or not video:
            logger.warning("demo publisher skipped: ffmpeg=%s video=%s", bool(ffmpeg), video)
            return False
        if not rtsp_port_open():
            logger.warning("demo publisher skipped: MediaMTX not listening on %s", DEMO_RTSP_PORT)
            return False

        with self._lock:
            if self._proc and self._proc.poll() is None:
                return True
            self._stop = False
            cmd = [
                ffmpeg,
                "-hide_banner",
                "-loglevel", "error",
                "-re",
                "-stream_loop", "-1",
                "-i", video,
                "-c", "copy",
                "-f", "rtsp",
                "-rtsp_transport", "tcp",
                DEMO_RTSP_URL,
            ]
            try:
                self._proc = subprocess.Popen(cmd, **popen_kwargs())
            except Exception:
                logger.exception("failed to start demo publisher")
                self._proc = None
                return False
            logger.info("demo publisher started pid=%s -> %s", self._proc.pid, DEMO_RTSP_URL)

        if not self._watch_thread or not self._watch_thread.is_alive():
            self._watch_thread = threading.Thread(target=self._watch, daemon=True, name="demo-rtsp-publisher")
            self._watch_thread.start()
        return True

    def _watch(self):
        while not self._stop:
            time.sleep(3)
            if not demo_publish_enabled():
                self.stop()
                break
            with self._lock:
                proc = self._proc
            if self._stop:
                break
            if proc is None or proc.poll() is None:
                continue
            logger.warning("demo publisher exited code=%s, restarting", proc.returncode)
            time.sleep(1)
            if not self._stop:
                self.ensure_started()

    def stop(self):
        self._stop = True
        with self._lock:
            proc = self._proc
            self._proc = None
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass


demo_publisher = DemoPublisher()
atexit.register(demo_publisher.stop)


def wire_cameras_to_demo_rtsp():
    """
    When DEMO_RTSP_PUBLISH=1, fill empty RTSP with mystream only.
    Never rewrite a real (including LAN) camera URL.
    """
    from apps.cameras.models import Camera

    if not demo_publish_enabled():
        return 0, Camera.objects.filter(enabled=True, status="online").count()

    qs = Camera.objects.filter(enabled=True, status="online")
    updated = 0
    for cam in qs:
        rtsp = (cam.rtsp or "").strip()
        if rtsp:
            continue
        cam.rtsp = DEMO_RTSP_URL
        cam.save(update_fields=["rtsp", "updated_at"])
        updated += 1
    return updated, qs.count()

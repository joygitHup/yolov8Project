"""MediaMTX helpers — native HLS URLs instead of Django data/hls remux."""
from __future__ import annotations

import http.cookiejar
import logging
import os
import socket
import urllib.error
import urllib.request
from urllib.parse import urlparse

logger = logging.getLogger("streaming.mediamtx")

_DEFAULT_HLS = "http://127.0.0.1:8888"
_DEFAULT_RTSP = "rtsp://127.0.0.1:8554"
_PROXY_PREFIX = "/mtx-hls"


def hls_base() -> str:
    return (os.environ.get("MEDIAMTX_HLS_BASE") or _DEFAULT_HLS).rstrip("/")


def rtsp_base() -> str:
    return (os.environ.get("MEDIAMTX_RTSP_BASE") or _DEFAULT_RTSP).rstrip("/")


def hls_port_open(timeout: float = 0.5) -> bool:
    parsed = urlparse(hls_base())
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8888
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def rtsp_port_open(timeout: float = 0.5) -> bool:
    parsed = urlparse(rtsp_base())
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8554
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def is_local_mediamtx_rtsp(rtsp: str) -> bool:
    """True when RTSP URL points at our MediaMTX instance."""
    url = (rtsp or "").strip()
    if not url.lower().startswith("rtsp://"):
        return False
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in ("127.0.0.1", "localhost", "::1"):
        return False
    base = urlparse(rtsp_base())
    base_port = base.port or 8554
    return (parsed.port or 554) == base_port


def path_from_rtsp(rtsp: str, camera_id: int | None = None) -> str:
    """Canonical MediaMTX path for this camera's RTSP. Empty RTSP → no path.

    Local MTX URLs keep their path (mystream, cam1, …). External cameras
    restream onto cam{id}. Never alias a LAN address to mystream.
    """
    url = (rtsp or "").strip()
    if not url.lower().startswith("rtsp://"):
        return ""
    if is_local_mediamtx_rtsp(url):
        parsed = urlparse(url)
        return (parsed.path or "").strip("/")
    if camera_id is not None:
        return f"cam{int(camera_id)}"
    return ""


def mtx_path_for(rtsp: str, camera_id: int | None = None) -> str:
    return path_from_rtsp(rtsp, camera_id)


def published_rtsp(rtsp: str, camera_id: int | None = None) -> str:
    """RTSP of the preview path — same stream HLS / evidence should use."""
    path = path_from_rtsp(rtsp, camera_id)
    if not path:
        return (rtsp or "").strip()
    return mtx_rtsp_url(path)


def mtx_rtsp_url(path: str) -> str:
    clean = str(path or "").strip("/")
    if not clean:
        return ""
    return f"{rtsp_base()}/{clean}"


def mtx_hls_url(path: str) -> str:
    """Frontend-relative HLS URL (proxied by Vite to MediaMTX :8888)."""
    clean = str(path or "").strip("/")
    if not clean:
        return ""
    return f"{_PROXY_PREFIX}/{clean}/index.m3u8"


def mtx_hls_absolute(path: str) -> str:
    clean = str(path or "").strip("/")
    if not clean:
        return ""
    return f"{hls_base()}/{clean}/index.m3u8"


def hls_ready(path: str, timeout: float = 3.0, check_port: bool = True) -> bool:
    """True when MediaMTX serves a usable playlist (follows cookie redirects)."""
    if not (path or "").strip("/"):
        return False
    if check_port and not hls_port_open(timeout=0.25):
        return False
    url = mtx_hls_absolute(path)
    if not url:
        return False
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    try:
        with opener.open(url, timeout=timeout) as resp:
            body = resp.read(512)
            text = body.decode("utf-8", errors="ignore")
            return "#EXTM3U" in text
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        logger.debug("hls_ready path=%s failed: %s", path, exc)
        return False


def wait_hls_ready(path: str, timeout: float = 12.0) -> bool:
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        if hls_ready(path, timeout=2.0):
            return True
        time.sleep(0.4)
    return False

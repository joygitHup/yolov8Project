"""MediaMTX helpers — native HLS URLs instead of Django data/hls remux."""
from __future__ import annotations

import http.cookiejar
import logging
import os
import socket
import threading
import urllib.error
import urllib.request
from urllib.parse import urlparse

logger = logging.getLogger("streaming.mediamtx")

_DEFAULT_HLS = "http://127.0.0.1:8888"
_DEFAULT_RTSP = "rtsp://127.0.0.1:8554"
_PROXY_PREFIX = "/media/mtx"


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
    """Same-origin HLS URL served by Django (requires login)."""
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


_mtx_proc = None
_mtx_lock = threading.Lock()


def _guess_bin() -> str:
    from pathlib import Path
    from django.conf import settings

    env = (os.environ.get("MEDIAMTX_BIN") or "").strip()
    if env and Path(env).is_file():
        return env
    root = Path(getattr(settings, "BASE_DIR", Path("."))).resolve().parent
    guesses = [
        Path(r"D:\applicationPath\ffmpegPath\mediamtx.exe"),
        root / "tools" / "mediamtx.exe",
        Path("mediamtx.exe"),
        Path("mediamtx"),
    ]
    for item in guesses:
        if item.is_file():
            return str(item)
    from shutil import which

    return which("mediamtx") or ""


def _yml_path() -> str:
    from pathlib import Path
    from django.conf import settings

    path = Path(getattr(settings, "DATA_DIR", Path("."))) / "mediamtx-8554.yml"
    return str(path) if path.is_file() else ""


def _start_docker() -> bool:
    import subprocess
    from pathlib import Path

    from django.conf import settings

    root = Path(getattr(settings, "BASE_DIR", Path("."))).resolve().parent
    compose = root / "docker-compose.yml"
    if not compose.is_file():
        return False
    try:
        proc = subprocess.run(
            ["docker", "compose", "--profile", "mtx", "up", "-d", "mediamtx"],
            cwd=str(root),
            timeout=40,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            logger.warning("mediamtx docker: %s", (proc.stderr or proc.stdout or "").strip())
            return False
        logger.info("mediamtx started via docker compose --profile mtx")
        return True
    except Exception as exc:
        logger.warning("mediamtx docker failed: %s", exc)
        return False


def _start_exe() -> bool:
    global _mtx_proc
    import subprocess
    from pathlib import Path

    from apps.streaming.ffmpeg import popen_kwargs

    bin_path = _guess_bin()
    yml = _yml_path()
    if not bin_path:
        logger.warning("MediaMTX binary not found. Set MEDIAMTX_BIN or use MEDIAMTX_MODE=docker.")
        return False
    args = [bin_path]
    if yml:
        args.append(yml)
    cwd = str(Path(bin_path).parent)
    try:
        _mtx_proc = subprocess.Popen(args, cwd=cwd, **popen_kwargs())
        logger.info("mediamtx exe pid=%s bin=%s", _mtx_proc.pid, bin_path)
        return True
    except Exception:
        logger.exception("mediamtx exe start failed")
        return False


def ensure_running(timeout: float = 8.0) -> bool:
    """Runtime-owned MediaMTX. Reuse :8554 if already up; else start exe or docker."""
    import time

    if rtsp_port_open(timeout=0.3) and hls_port_open(timeout=0.3):
        return True
    mode = (os.environ.get("MEDIAMTX_MODE") or "exe").strip().lower()
    with _mtx_lock:
        if rtsp_port_open(timeout=0.2):
            return True
        started = _start_docker() if mode in ("docker", "compose") else _start_exe()
        if not started and mode != "docker":
            started = _start_docker()
    deadline = time.time() + max(2.0, timeout)
    while time.time() < deadline:
        if rtsp_port_open(timeout=0.3):
            return True
        time.sleep(0.3)
    logger.warning("MediaMTX did not listen on 8554 after start (mode=%s)", mode)
    return rtsp_port_open(timeout=0.3)


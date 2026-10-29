"""Rolling MPEG-TS GOP buffer from the published MediaMTX RTSP.

Runtime-only. Alert clips concat the last ~12s of copy-mode segments so the
event itself is in the file, instead of JPEG-stitching after the fact.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from django.conf import settings

logger = logging.getLogger("streaming.preroll")

_SEGMENT_SEC = 1
_WRAP = 12  # default buffer; overridden by settings.streaming.prerollSeconds
_SAFE = re.compile(r"[^A-Za-z0-9_.-]+")
_lock = threading.Lock()
_procs: dict[str, subprocess.Popen] = {}
_src: dict[str, str] = {}
_last_restart: dict[str, float] = {}


def _wrap_count() -> int:
    """Read buffer length from settings.streaming.prerollSeconds, default 12."""
    try:
        from apps.systemcfg.services import get_section

        secs = int(get_section("streaming").get("prerollSeconds") or _WRAP)
    except Exception:
        secs = _WRAP
    return max(3, min(secs, 60))


def _root() -> Path:
    path = Path(settings.DATA_DIR) / "hls" / "preroll"
    path.mkdir(parents=True, exist_ok=True)
    return path


def dir_for(mtx_path: str) -> Path:
    slug = _SAFE.sub("_", (mtx_path or "").strip())[:64] or "unknown"
    path = _root() / slug
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure(mtx_path: str, src_rtsp: str) -> None:
    """Keep a copy-mode segment ring on `src_rtsp` (published MTX URL)."""
    from apps.streaming.ffmpeg import find_ffmpeg, popen_kwargs

    path = (mtx_path or "").strip()
    src = (src_rtsp or "").strip()
    ffmpeg = find_ffmpeg()
    if not path or not src or not ffmpeg:
        return
    with _lock:
        proc = _procs.get(path)
        if proc is not None and proc.poll() is None and _src.get(path) == src:
            return
        if proc is not None and proc.poll() is None:
            _kill(proc)
        out_dir = dir_for(path)
        pattern = str(out_dir / "seg_%03d.ts")
        cmd = [
            ffmpeg,
            "-hide_banner",
            "-loglevel", "error",
            "-rtsp_transport", "tcp",
            "-i", src,
            "-an",
            "-c:v", "copy",
            "-f", "segment",
            "-segment_time", str(_SEGMENT_SEC),
            "-segment_wrap", str(_wrap_count()),
            "-reset_timestamps", "1",
            "-strftime", "0",
            pattern,
        ]
        try:
            proc = subprocess.Popen(cmd, **popen_kwargs())
            _procs[path] = proc
            _src[path] = src
            logger.info("preroll start path=%s pid=%s", path, proc.pid)
        except Exception:
            logger.exception("preroll start failed path=%s", path)


def reconcile() -> int:
    """
    Runtime sweep: restart buffer processes that died so the pre-event window
    refills immediately instead of waiting for the next 30s stream reconcile.
    Throttled per source (10s) so a permanently broken RTSP source doesn't
    spawn ffmpeg on every tick.
    """
    now = time.monotonic()
    with _lock:
        items = list(_procs.items())
        srcs = dict(_src)
    restarted = 0
    for path, proc in items:
        try:
            if proc.poll() is None:
                continue
            if now - _last_restart.get(path, 0.0) < 10.0:
                continue
            src = srcs.get(path) or ""
            logger.warning("preroll died path=%s code=%s, restarting", path, proc.returncode)
            _last_restart[path] = now
            ensure(path, src)
            restarted += 1
        except Exception:
            logger.exception("preroll restart failed path=%s", path)
    return restarted


def stop(mtx_path: str) -> None:
    path = (mtx_path or "").strip()
    with _lock:
        proc = _procs.pop(path, None)
        _src.pop(path, None)
    _kill(proc)


def stop_all() -> None:
    with _lock:
        items = list(_procs.items())
        _procs.clear()
        _src.clear()
    for _, proc in items:
        _kill(proc)


def concat_mp4(mtx_path: str) -> bytes | None:
    """Oldest-to-newest copy of the current ring → MP4."""
    from apps.streaming.ffmpeg import find_ffmpeg, popen_kwargs

    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return None
    files = _ordered_segments(mtx_path)
    if not files:
        return None
    list_path = None
    out_path = None
    try:
        fd, list_name = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        list_path = Path(list_name)
        lines = []
        for item in files:
            escaped = str(item).replace("\\", "/").replace("'", r"'\''")
            lines.append(f"file '{escaped}'")
        list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        fd, out_name = tempfile.mkstemp(suffix=".mp4")
        os.close(fd)
        out_path = Path(out_name)
        common = [
            ffmpeg, "-hide_banner", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(list_path), "-an",
        ]
        attempts = [
            (25, ["-c", "copy", "-movflags", "+faststart", "-y", str(out_path)]),
            (
                40,
                [
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", "-y", str(out_path),
                ],
            ),
        ]
        for timeout, extra in attempts:
            try:
                if out_path.exists():
                    out_path.unlink()
            except Exception:
                pass
            proc = subprocess.run(common + extra, timeout=timeout, **popen_kwargs())
            if proc.returncode == 0 and out_path.is_file() and out_path.stat().st_size > 2048:
                return out_path.read_bytes()
        logger.warning("preroll concat failed path=%s", mtx_path)
        return None
    except Exception as exc:
        logger.warning("preroll concat error path=%s: %s", mtx_path, exc)
        return None
    finally:
        for p in (list_path, out_path):
            if p is None:
                continue
            try:
                p.unlink(missing_ok=True)
            except Exception:
                pass


def _ordered_segments(mtx_path: str) -> list[Path]:
    folder = dir_for(mtx_path)
    items = [p for p in folder.glob("seg_*.ts") if p.is_file() and p.stat().st_size > 200]
    items.sort(key=lambda p: p.stat().st_mtime)
    now = time.time()
    items = [p for p in items if now - p.stat().st_mtime < 30]
    return items[-_wrap_count():]


def _kill(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=1)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass

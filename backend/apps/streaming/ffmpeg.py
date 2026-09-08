import os
import shutil
import subprocess
from pathlib import Path

from django.conf import settings

_FFMPEG_CACHE = None


def find_ffmpeg():
    global _FFMPEG_CACHE
    if _FFMPEG_CACHE:
        return _FFMPEG_CACHE
    env = (os.environ.get("FFMPEG_PATH") or "").strip()
    if env and Path(env).exists():
        _FFMPEG_CACHE = env
        return _FFMPEG_CACHE
    found = shutil.which("ffmpeg")
    if found:
        _FFMPEG_CACHE = found
        return _FFMPEG_CACHE
    candidates = [
        r"D:\applicationPath\ffmpegPath\ffmpeg-master-latest-win64-gpl-shared\bin\ffmpeg.exe",
        r"D:\applicationPath\EVpath\EVCapture\ffmpeg.exe",
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
        "/usr/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
    ]
    for path in candidates:
        if Path(path).exists():
            _FFMPEG_CACHE = path
            return _FFMPEG_CACHE
    return None


def hls_root():
    root = Path(settings.DATA_DIR) / "hls"
    root.mkdir(parents=True, exist_ok=True)
    return root


def camera_hls_dir(camera_id):
    path = hls_root() / str(int(camera_id))
    path.mkdir(parents=True, exist_ok=True)
    return path


def playlist_path(camera_id):
    return camera_hls_dir(camera_id) / "index.m3u8"


def hls_url(camera_id):
    """Legacy local-disk HLS URL (fallback only)."""
    return f"/media/hls/{int(camera_id)}/index.m3u8"


def build_publish_cmd(ffmpeg_bin, video_path, rtsp_url):
    """Publish a local MP4 loop to MediaMTX via RTSP (demo mystream only)."""
    return [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel", "error",
        "-re",
        "-stream_loop", "-1",
        "-i", video_path,
        "-an",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-tune", "zerolatency",
        "-pix_fmt", "yuv420p",
        "-profile:v", "baseline",
        "-g", "24",
        "-f", "rtsp",
        "-rtsp_transport", "tcp",
        rtsp_url,
    ]


def build_restream_cmd(ffmpeg_bin, src_rtsp, dst_rtsp):
    """Copy an external camera RTSP onto a MediaMTX path (same pixels as preview)."""
    return [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel", "error",
        "-rtsp_transport", "tcp",
        "-fflags", "nobuffer+genpts",
        "-flags", "low_delay",
        "-probesize", "32768",
        "-analyzeduration", "500000",
        "-i", src_rtsp,
        "-an",
        "-c:v", "copy",
        "-f", "rtsp",
        "-rtsp_transport", "tcp",
        dst_rtsp,
    ]


def popen_kwargs():
    kwargs = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return kwargs


def _escape_drawtext(text):
    return (
        str(text or "")
        .replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "%%")
    )


def demo_video_path():
    env = (os.environ.get("FFMPEG_DEMO_VIDEO") or os.environ.get("DEMO_VIDEO_PATH") or "").strip()
    if env and Path(env).exists():
        return env
    # Prefer the user's demo clip used for MediaMTX push
    for candidate in (
        Path(r"D:\applicationPath\ffmpegPath\vide02.mp4"),
        Path(r"D:\applicationPath\ffmpegPath\com.mp4"),
    ):
        if candidate.exists():
            return str(candidate)
    return None


def build_file_loop_cmd(ffmpeg_bin, video_path, out_m3u8):
    """Loop local MP4 with stream copy (low CPU) for simulated camera feed."""
    return [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel", "error",
        "-re",
        "-stream_loop", "-1",
        "-i", video_path,
        "-an",
        "-c:v", "copy",
        "-bsf:v", "h264_mp4toannexb",
        "-f", "hls",
        "-hls_time", "2",
        "-hls_list_size", "5",
        "-hls_flags", "delete_segments+append_list",
        "-hls_allow_cache", "0",
        str(out_m3u8),
    ]


def build_demo_cmd(ffmpeg_bin, camera, out_m3u8, with_text=True):
    label = _escape_drawtext(camera.name or f"CAM-{camera.id}")
    loc = _escape_drawtext(camera.location or camera.ip or "")
    cmd = [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel", "error",
        "-re",
        "-f", "lavfi",
        "-i", "testsrc=size=640x360:rate=10",
    ]
    if with_text:
        video_filter = (
            f"drawtext=text='{label}':fontsize=22:fontcolor=white:x=16:y=16:"
            f"box=1:boxcolor=black@0.45,"
            f"drawtext=text='{loc}':fontsize=14:fontcolor=white:x=16:y=48:"
            f"box=1:boxcolor=black@0.35"
        )
        cmd.extend(["-vf", video_filter])
    cmd.extend([
        "-an",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-tune", "zerolatency",
        "-pix_fmt", "yuv420p",
        "-g", "20",
        "-f", "hls",
        "-hls_time", "2",
        "-hls_list_size", "4",
        "-hls_flags", "delete_segments+append_list",
        "-hls_allow_cache", "0",
        str(out_m3u8),
    ])
    return cmd


def build_rtsp_cmd(ffmpeg_bin, camera, out_m3u8):
    # Prefer copy to keep CPU low; remux into HLS.
    # Low probesize helps first playlist appear quickly under laggy publishers.
    return [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel", "error",
        "-rtsp_transport", "tcp",
        "-fflags", "nobuffer+genpts",
        "-flags", "low_delay",
        "-probesize", "32768",
        "-analyzeduration", "500000",
        "-i", camera.rtsp,
        "-an",
        "-c:v", "copy",
        "-bsf:v", "h264_mp4toannexb",
        "-f", "hls",
        "-hls_time", "2",
        "-hls_list_size", "5",
        "-hls_flags", "delete_segments+append_list",
        "-hls_allow_cache", "0",
        str(out_m3u8),
    ]

import mimetypes
from pathlib import Path

from django.http import FileResponse, Http404
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from apps.common.apiview import APIView

from apps.cameras.models import Camera
from apps.common.permissions import IsAdminOrOperator
from apps.streaming.ffmpeg import camera_hls_dir, find_ffmpeg, hls_url
from apps.streaming.manager import stream_manager
from apps.streaming.publisher import DEMO_RTSP_URL, demo_publisher


def _camera_or_404(pk):
    camera = Camera.objects.filter(pk=pk).first()
    if not camera:
        raise NotFound("摄像头不存在")
    return camera


class CameraStreamView(APIView):
    def get(self, request, pk):
        _camera_or_404(pk)
        data = stream_manager.status(pk)
        data["ffmpegAvailable"] = bool(find_ffmpeg())
        data["demoPublisher"] = demo_publisher.running
        data["demoRtsp"] = DEMO_RTSP_URL
        return Response(data)


class CameraStreamStartView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        camera = _camera_or_404(pk)
        if not camera.enabled or camera.status != "online":
            raise ValidationError("摄像头离线或未启用，无法启动视频流")
        if not (camera.rtsp or "").strip():
            raise ValidationError("未配置 RTSP，无法启动预览流")
        prefer_rtsp = request.data.get("preferRtsp", True)
        wait_raw = request.data.get("wait")
        wait = False if wait_raw is None else bool(wait_raw)
        try:
            data = stream_manager.start_async(camera, prefer_rtsp=bool(prefer_rtsp))
            if wait:
                data = stream_manager.status(camera.id)
        except RuntimeError as exc:
            raise ValidationError(str(exc)) from exc
        data["ffmpegAvailable"] = bool(find_ffmpeg())
        data["demoPublisher"] = demo_publisher.running
        data["demoRtsp"] = DEMO_RTSP_URL
        return Response(data)


class CameraStreamStopView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        _camera_or_404(pk)
        data = stream_manager.stop(pk)
        data["ffmpegAvailable"] = bool(find_ffmpeg())
        return Response(data)


class HlsMediaView(APIView):
    """Serve HLS playlist/segments. Requires login (JWT header or access cookie)."""
    permission_classes = [IsAuthenticated]

    def get(self, request, camera_id, filename):
        # prevent path traversal
        name = Path(filename).name
        if name != filename or ".." in filename:
            raise Http404()
        base = camera_hls_dir(camera_id).resolve()
        target = (base / name).resolve()
        if not str(target).startswith(str(base)) or not target.exists() or not target.is_file():
            raise Http404()
        content_type = mimetypes.guess_type(str(target))[0]
        if name.endswith(".m3u8"):
            content_type = "application/vnd.apple.mpegurl"
        elif name.endswith(".ts"):
            content_type = "video/mp2t"
        response = FileResponse(open(target, "rb"), content_type=content_type or "application/octet-stream")
        response["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response


class AlertMediaView(APIView):
    """Serve alert snapshot/clip files. Requires login (JWT header or access cookie)."""
    permission_classes = [IsAuthenticated]

    def get(self, request, alert_id, filename):
        from apps.common.storage import open_response

        response = open_response(alert_id, filename)
        if not response:
            raise Http404()
        return response


class MtxHlsProxyView(APIView):
    """Proxy MediaMTX HLS so playlists never hit :8888 without a logged-in session."""
    permission_classes = [IsAuthenticated]

    def get(self, request, mtx_path, filename):
        import re
        import urllib.error
        import urllib.request

        from django.http import HttpResponse
        from apps.streaming import mediamtx as mtx

        path = str(mtx_path or "").strip("/")
        name = Path(filename).name
        if not path or name != filename or ".." in path or ".." in filename:
            raise Http404()
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", path) or not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
            raise Http404()
        upstream = f"{mtx.hls_base()}/{path}/{name}"
        try:
            with urllib.request.urlopen(upstream, timeout=8) as resp:
                data = resp.read()
                content_type = resp.headers.get("Content-Type") or "application/octet-stream"
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
            raise Http404() from None
        if name.endswith(".m3u8"):
            content_type = "application/vnd.apple.mpegurl"
            text = data.decode("utf-8", errors="ignore")
            data = _rewrite_mtx_playlist(text, path).encode("utf-8")
        elif name.endswith(".ts"):
            content_type = "video/mp2t"
        response = HttpResponse(data, content_type=content_type)
        response["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response


def _rewrite_mtx_playlist(text: str, mtx_path: str) -> str:
    prefix = f"/media/mtx/{mtx_path}/"
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            from urllib.parse import urlparse

            parsed = urlparse(stripped)
            if parsed.scheme or stripped.startswith("/"):
                lines.append(prefix + Path(parsed.path or stripped).name)
                continue
        lines.append(line)
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")

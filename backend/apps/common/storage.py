"""Alert evidence storage: MinIO (default) with local disk fallback."""
from __future__ import annotations

import io
import logging
import threading
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, StreamingHttpResponse

logger = logging.getLogger("common.storage")

_client = None
_client_lock = threading.Lock()
_bucket_ready = False


def media_url(alert_id: int, filename: str) -> str:
    return f"/media/alerts/{int(alert_id)}/{filename}"


def object_key(alert_id: int, filename: str) -> str:
    name = Path(filename).name
    return f"alerts/{int(alert_id)}/{name}"


def alerts_media_root() -> Path:
    root = Path(settings.DATA_DIR) / "alerts"
    root.mkdir(parents=True, exist_ok=True)
    return root


def alert_dir(alert_id: int) -> Path:
    path = alerts_media_root() / str(int(alert_id))
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_local_file(alert_id: int, filename: str) -> Path | None:
    name = Path(filename).name
    if name != filename or ".." in filename:
        return None
    base = (alerts_media_root() / str(int(alert_id))).resolve()
    target = (base / name).resolve()
    if not str(target).startswith(str(base)) or not target.is_file():
        return None
    return target


def _minio_enabled() -> bool:
    backend = (getattr(settings, "EVIDENCE_BACKEND", "minio") or "minio").lower()
    return backend not in ("local", "disk", "file")


def _client_or_none():
    global _client, _bucket_ready
    if not _minio_enabled():
        return None
    if _client is not None:
        return _client
    with _client_lock:
        if _client is not None:
            return _client
        try:
            from minio import Minio

            endpoint = (getattr(settings, "MINIO_ENDPOINT", None) or "127.0.0.1:9000").strip()
            client = Minio(
                endpoint,
                access_key=getattr(settings, "MINIO_ACCESS_KEY", "") or "Admin",
                secret_key=getattr(settings, "MINIO_SECRET_KEY", "") or "Admin123",
                secure=bool(getattr(settings, "MINIO_SECURE", False)),
            )
            bucket = getattr(settings, "MINIO_BUCKET", "yolov8pro")
            if not client.bucket_exists(bucket):
                client.make_bucket(bucket)
                logger.info("minio bucket created %s", bucket)
            _bucket_ready = True
            _client = client
            logger.info("minio connected %s bucket=%s", endpoint, bucket)
            return _client
        except Exception as exc:
            logger.warning("minio unavailable: %s", exc)
            _client = None
            return None


def ping() -> dict:
    info = {
        "backend": "minio" if _minio_enabled() else "local",
        "endpoint": getattr(settings, "MINIO_ENDPOINT", ""),
        "bucket": getattr(settings, "MINIO_BUCKET", ""),
        "ok": False,
    }
    if not _minio_enabled():
        info["ok"] = True
        info["backend"] = "local"
        return info
    client = _client_or_none()
    if client is None:
        return info
    try:
        info["ok"] = bool(client.bucket_exists(info["bucket"]))
    except Exception as exc:
        info["error"] = str(exc)
    return info


def put_bytes(alert_id: int, filename: str, data: bytes, content_type: str) -> str | None:
    """Store evidence; return public media URL or None."""
    if not data:
        return None
    name = Path(filename).name
    if _minio_enabled():
        client = _client_or_none()
        if client is not None:
            try:
                bucket = getattr(settings, "MINIO_BUCKET", "yolov8pro")
                key = object_key(alert_id, name)
                client.put_object(
                    bucket,
                    key,
                    io.BytesIO(data),
                    length=len(data),
                    content_type=content_type or "application/octet-stream",
                )
                return media_url(alert_id, name)
            except Exception:
                logger.exception("minio put failed alert=%s file=%s", alert_id, name)
    try:
        out = alert_dir(alert_id) / name
        out.write_bytes(data)
        return media_url(alert_id, name)
    except Exception:
        logger.exception("local put failed alert=%s file=%s", alert_id, name)
        return None


def put_key(key: str, data: bytes, content_type: str) -> str | None:
    """Store an arbitrary object; return the key on success."""
    safe = _safe_object_key(key)
    if not safe or not data:
        return None
    if _minio_enabled():
        client = _client_or_none()
        if client is not None:
            try:
                bucket = getattr(settings, "MINIO_BUCKET", "yolov8pro")
                client.put_object(
                    bucket,
                    safe,
                    io.BytesIO(data),
                    length=len(data),
                    content_type=content_type or "application/octet-stream",
                )
                return safe
            except Exception:
                logger.exception("minio put_key failed key=%s", safe)
    try:
        out = Path(settings.DATA_DIR) / safe
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        return safe
    except Exception:
        logger.exception("local put_key failed key=%s", safe)
        return None


def _safe_object_key(key: str) -> str | None:
    text = (key or "").replace("\\", "/").strip().lstrip("/")
    if not text or ".." in text.split("/"):
        return None
    return text


def put_file(alert_id: int, filename: str, path: Path, content_type: str) -> str | None:
    path = Path(path)
    if not path.is_file():
        return None
    return put_bytes(alert_id, filename, path.read_bytes(), content_type)


def get_bytes(key: str) -> bytes | None:
    safe = _safe_object_key(key)
    if not safe:
        return None
    client = _client_or_none()
    if client is not None:
        try:
            obj = client.get_object(getattr(settings, "MINIO_BUCKET", "yolov8pro"), safe)
            try:
                return obj.read()
            finally:
                try:
                    obj.close()
                except Exception:
                    pass
                try:
                    obj.release_conn()
                except Exception:
                    pass
        except Exception:
            pass
    local = Path(settings.DATA_DIR) / safe
    if local.is_file():
        return local.read_bytes()
    return None


def exists(alert_id: int, filename: str) -> bool:
    name = Path(filename).name
    if _minio_enabled():
        client = _client_or_none()
        if client is not None:
            try:
                client.stat_object(getattr(settings, "MINIO_BUCKET", "yolov8pro"), object_key(alert_id, name))
                return True
            except Exception:
                pass
    return bool(resolve_local_file(alert_id, name))


def open_response(alert_id: int, filename: str):
    """Django HTTP response for <img>/<video>, or None if missing.

    MinIO first so a stale local mosaic JPEG cannot shadow a new object.
    """
    import mimetypes

    name = Path(filename).name
    content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    client = _client_or_none() if _minio_enabled() else None
    if client is not None:
        try:
            obj = client.get_object(
                getattr(settings, "MINIO_BUCKET", "yolov8pro"),
                object_key(alert_id, name),
            )
        except Exception:
            obj = None
        if obj is not None:

            def _stream():
                try:
                    for chunk in obj.stream(32 * 1024):
                        yield chunk
                finally:
                    try:
                        obj.close()
                    except Exception:
                        pass
                    try:
                        obj.release_conn()
                    except Exception:
                        pass

            response = StreamingHttpResponse(_stream(), content_type=content_type)
            response["Cache-Control"] = "public, max-age=3600"
            response["Access-Control-Allow-Origin"] = "*"
            return response

    local = resolve_local_file(alert_id, name)
    if local:
        response = FileResponse(open(local, "rb"), content_type=content_type)
        response["Cache-Control"] = "public, max-age=3600"
        response["Access-Control-Allow-Origin"] = "*"
        return response
    return None

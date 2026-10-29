"""HTTP client for the external YOLO RTSP inference service."""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any

import urllib.error
import urllib.request
import json

logger = logging.getLogger("inference.remote")


def service_url() -> str:
    return (os.environ.get("YOLO_SERVICE_URL") or "http://127.0.0.1:8090").rstrip("/")


def ingest_callback_url() -> str:
    return (
        os.environ.get("YOLO_INGEST_URL")
        or "http://127.0.0.1:3001/api/inference/ingest"
    ).strip()


def ingest_token() -> str:
    try:
        from django.conf import settings

        text = str(getattr(settings, "INGEST_TOKEN", "") or "").strip()
        if text:
            return text
    except Exception:
        pass
    return (os.environ.get("INGEST_TOKEN") or "").strip()


def ingest_tokens_accepted() -> list[str]:
    """
    Return list of ingest tokens accepted by the Django side. Used for
    token rotation: set INGEST_TOKEN_NEXT to switch over gracefully.
    """
    tokens = [ingest_token()]
    # Accept old token during rotation
    next_val = (os.environ.get("INGEST_TOKEN_NEXT") or "").strip()
    if next_val and next_val not in tokens:
        tokens.append(next_val)
    return [t for t in tokens if t]


def infer_mode() -> str:
    """Always remote. In-process YOLO races Kafka ingest and is not supported."""
    raw = (os.environ.get("YOLO_INFER_MODE") or "remote").strip().lower()
    if raw == "local" or os.environ.get("YOLO_ALLOW_LOCAL", "").strip():
        logger.warning("in-process YOLO is disabled; using remote yolo-service + Kafka")
    return "remote"


def _request(method: str, path: str, body: dict | None = None, timeout: float = 8.0) -> dict[str, Any]:
    url = f"{service_url()}{path}"
    data = None
    headers = {"Accept": "application/json", "X-Ingest-Token": ingest_token()}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"YOLO service HTTP {exc.code}: {detail}") from exc
    except Exception as exc:
        raise RuntimeError(f"YOLO service unreachable: {exc}") from exc


def health() -> dict[str, Any] | None:
    try:
        return _request("GET", "/health", timeout=3.0)
    except Exception as exc:
        logger.debug("yolo health failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Face library proxy (enrollment is done by yolo-service which owns insightface)
# ---------------------------------------------------------------------------

def list_faces() -> list[dict[str, Any]]:
    return _request("GET", "/faces", timeout=10.0).get("list") or []


def delete_face(face_id: str) -> dict[str, Any]:
    return _request("DELETE", f"/faces/{face_id}", timeout=10.0)


def enroll_face(name: str, file_bytes: bytes, filename: str = "upload.jpg",
                content_type: str = "image/jpeg", timeout: float = 60.0) -> dict[str, Any]:
    """Multipart upload to yolo-service /faces/enroll (stdlib-only multipart)."""
    import uuid as _uuid

    safe_name = "".join(c if c.isascii() and c.isalnum() or c in "._-" else "_" for c in filename) or "upload.jpg"
    boundary = f"----yolo{_uuid.uuid4().hex}"
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="name"\r\n\r\n{name}\r\n'.encode("utf-8"),
        (f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{safe_name}"\r\n'
         f'Content-Type: {content_type or "application/octet-stream"}\r\n\r\n').encode("utf-8"),
        file_bytes,
        b"\r\n",
        f"--{boundary}--\r\n".encode("utf-8"),
    ]
    url = f"{service_url()}/faces/enroll"
    req = urllib.request.Request(
        url, data=b"".join(parts), method="POST",
        headers={
            "Accept": "application/json",
            "X-Ingest-Token": ingest_token(),
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"YOLO service HTTP {exc.code}: {detail}") from exc
    except Exception as exc:
        raise RuntimeError(f"YOLO service unreachable: {exc}") from exc


@lru_cache(maxsize=64)
def _fetch_face_photo(face_id: str) -> bytes | None:
    """Photos are immutable per faceId (uuid-based) — cache bytes in-process.
    Entries for deleted faces simply go unused (row disappears from the list)."""
    url = f"{service_url()}/faces/{face_id}/photo"
    req = urllib.request.Request(url, headers={"X-Ingest-Token": ingest_token()}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            return resp.read()
    except Exception:
        return None


def face_photo(face_id: str, timeout: float = 8.0) -> bytes | None:
    return _fetch_face_photo(face_id)


def start_camera(
    *,
    camera_id: int,
    rtsp: str,
    conf: float,
    iou: float,
    max_det: int,
    fps: float,
    model_path: str | None = None,
) -> dict[str, Any]:
    body = {
        "cameraId": int(camera_id),
        "rtsp": rtsp,
        "conf": conf,
        "iou": iou,
        "maxDet": max_det,
        "fps": fps,
        "modelPath": model_path,
        "callbackUrl": ingest_callback_url(),
        "ingestToken": ingest_token(),
    }
    return _request("POST", "/cameras/start", body)


def stop_camera(camera_id: int) -> dict[str, Any]:
    return _request("POST", "/cameras/stop", {"cameraId": int(camera_id)})


def stop_all() -> dict[str, Any]:
    return _request("POST", "/cameras/stop-all", {})


def reload_model(model_path: str | None = None) -> dict[str, Any]:
    body = {"modelPath": model_path} if model_path else {}
    return _request("POST", "/model/reload", body, timeout=60.0)


def list_cameras() -> list[dict[str, Any]]:
    data = _request("GET", "/cameras")
    return list(data.get("list") or [])

"""HTTP client for the external YOLO RTSP inference service."""
from __future__ import annotations

import logging
import os
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

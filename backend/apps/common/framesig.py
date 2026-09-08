"""HMAC for Kafka detect.frames so LAN producers cannot inject detections."""
from __future__ import annotations

import hashlib
import hmac
import json


def _canonical(payload: dict) -> bytes:
    body = {
        "cameraId": payload.get("cameraId"),
        "detections": payload.get("detections") or [],
        "fps": payload.get("fps"),
        "inferActive": payload.get("inferActive", True),
        "modelReady": payload.get("modelReady", True),
        "timestamp": payload.get("timestamp"),
    }
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def sign_frame(payload: dict, secret: str) -> str:
    text = (secret or "").strip()
    if not text:
        return ""
    return hmac.new(text.encode("utf-8"), _canonical(payload), hashlib.sha256).hexdigest()


def verify_frame(payload: dict, secret: str, signature: str) -> bool:
    expected = sign_frame(payload, secret)
    got = (signature or "").strip()
    if not expected or not got:
        return False
    return hmac.compare_digest(expected, got)

"""Produce detection events to Kafka (no JPEG). HTTP ingest is fallback only."""
from __future__ import annotations

import json
import logging
import os
import threading

logger = logging.getLogger("yolo.bus")

_producer = None
_lock = threading.Lock()
_failed = False


def bootstrap() -> str:
    return (os.environ.get("KAFKA_BOOTSTRAP") or "127.0.0.1:9092").strip()


def topic_frames() -> str:
    return (os.environ.get("KAFKA_TOPIC_FRAMES") or "yolov8.detect.frames").strip()


def enabled() -> bool:
    raw = (os.environ.get("KAFKA_ENABLED") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _get_producer():
    global _producer, _failed
    if not enabled():
        return None
    if _failed:
        return None
    if _producer is not None:
        return _producer
    with _lock:
        if _producer is not None or _failed:
            return _producer
        try:
            from kafka import KafkaProducer

            _producer = KafkaProducer(
                bootstrap_servers=bootstrap().split(","),
                value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
                key_serializer=lambda k: (k or "").encode("utf-8"),
                acks="all",
                linger_ms=20,
                retries=2,
                max_block_ms=2500,
                request_timeout_ms=5000,
            )
            logger.info("kafka producer %s topic=%s", bootstrap(), topic_frames())
            return _producer
        except Exception as exc:
            _failed = True
            logger.warning("kafka producer unavailable: %s", exc)
            return None


def produce_frame(payload: dict) -> bool:
    """Publish detect.frames. Returns False so caller can HTTP-fallback."""
    prod = _get_producer()
    if prod is None:
        return False
    secret = (payload.get("ingestToken") or "").strip()
    if not secret:
        from app.auth import service_token

        secret = service_token()
    if not secret:
        logger.warning("kafka produce skipped: missing ingest token")
        return False
    try:
        from app.framesig import sign_frame

        body = {
            "cameraId": payload.get("cameraId"),
            "timestamp": payload.get("timestamp"),
            "fps": payload.get("fps"),
            "detections": payload.get("detections") or [],
            "modelReady": payload.get("modelReady", True),
            "inferActive": payload.get("inferActive", True),
        }
        body["sig"] = sign_frame(body, secret)
        key = str(body.get("cameraId") or "")
        fut = prod.send(topic_frames(), value=body, key=key)
        fut.get(timeout=4)
        return True
    except Exception as exc:
        logger.warning("kafka produce failed: %s", exc)
        return False

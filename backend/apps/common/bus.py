"""Kafka event bus: detection frames and alert facts.

Topics (defaults):
  yolov8.detect.frames   lightweight detections (no JPEG)
  yolov8.alerts.created  alert row after DB insert

JSON only. Latest preview JPEG stays in Redis.
"""
from __future__ import annotations

import json
import logging
import threading

logger = logging.getLogger("common.bus")

_producer = None
_producer_lock = threading.Lock()
_stop = threading.Event()
_threads: list[threading.Thread] = []


def bootstrap() -> str:
    from django.conf import settings

    return (getattr(settings, "KAFKA_BOOTSTRAP", None) or "127.0.0.1:9092").strip()


def enabled() -> bool:
    from django.conf import settings

    raw = (getattr(settings, "KAFKA_ENABLED", True))
    if isinstance(raw, str):
        return raw.strip().lower() not in ("0", "false", "no", "off")
    return bool(raw)


def topic_frames() -> str:
    from django.conf import settings

    return (getattr(settings, "KAFKA_TOPIC_FRAMES", None) or "yolov8.detect.frames").strip()


def topic_alerts() -> str:
    from django.conf import settings

    return (getattr(settings, "KAFKA_TOPIC_ALERTS", None) or "yolov8.alerts.created").strip()


def _get_producer():
    global _producer
    if _producer is not None:
        return _producer
    with _producer_lock:
        if _producer is not None:
            return _producer
        from django.core.serializers.json import DjangoJSONEncoder
        from kafka import KafkaProducer

        _producer = KafkaProducer(
            bootstrap_servers=bootstrap().split(","),
            value_serializer=lambda v: json.dumps(
                v, ensure_ascii=False, cls=DjangoJSONEncoder
            ).encode("utf-8"),
            key_serializer=lambda k: (k or "").encode("utf-8"),
            acks="all",
            linger_ms=20,
            retries=3,
            max_block_ms=4000,
            request_timeout_ms=8000,
        )
        logger.info("kafka producer %s", bootstrap())
        return _producer


def produce(topic: str, value: dict, key: str | None = None) -> None:
    if not enabled():
        raise RuntimeError("kafka disabled")
    prod = _get_producer()
    fut = prod.send(topic, value=value, key=str(key or ""))
    fut.get(timeout=8)


def produce_frame(payload: dict) -> None:
    cid = payload.get("cameraId")
    produce(topic_frames(), payload, key=str(cid or ""))


def produce_alert(payload: dict) -> None:
    from django.core.serializers.json import DjangoJSONEncoder

    aid = payload.get("id") or payload.get("alertId")
    safe = json.loads(json.dumps(payload, cls=DjangoJSONEncoder))
    produce(topic_alerts(), safe, key=str(aid or ""))


def start_frames_consumer(handler) -> None:
    """Runtime: consume detect.frames and call handler(dict)."""
    if not enabled():
        logger.info("kafka consumer skipped (disabled)")
        return
    if any(t.is_alive() for t in _threads):
        return
    _stop.clear()
    t = threading.Thread(target=_consume_loop, args=(topic_frames(), handler), name="kafka-detect-frames", daemon=True)
    t.start()
    _threads.append(t)
    logger.info("kafka consumer topic=%s group=yolov8-runtime", topic_frames())


def stop_consumers() -> None:
    _stop.set()
    global _producer
    with _producer_lock:
        if _producer is not None:
            try:
                _producer.flush(timeout=2)
                _producer.close(timeout=2)
            except Exception:
                pass
            _producer = None


def _consume_loop(topic: str, handler) -> None:
    from kafka import KafkaConsumer
    from kafka.errors import KafkaError

    while not _stop.is_set():
        consumer = None
        try:
            consumer = KafkaConsumer(
                topic,
                bootstrap_servers=bootstrap().split(","),
                group_id="yolov8-runtime",
                enable_auto_commit=False,
                auto_offset_reset="earliest",
                value_deserializer=lambda b: json.loads(b.decode("utf-8")) if b else {},
                key_deserializer=lambda b: b.decode("utf-8") if b else "",
                consumer_timeout_ms=1000,
                max_poll_records=32,
            )
            logger.info("kafka consuming %s", topic)
            while not _stop.is_set():
                records = consumer.poll(timeout_ms=1000)
                if not records:
                    continue
                for _tp, batch in records.items():
                    for rec in batch:
                        try:
                            payload = _authorized_frame(rec.value or {})
                            if payload is None:
                                continue
                            handler(payload)
                        except Exception:
                            logger.exception("kafka handler failed topic=%s offset=%s", topic, rec.offset)
                try:
                    consumer.commit()
                except Exception:
                    logger.warning("kafka commit failed", exc_info=True)
        except KafkaError as exc:
            logger.warning("kafka consumer reconnect: %s", exc)
        except Exception as exc:
            logger.warning("kafka consumer error: %s", exc)
        finally:
            try:
                if consumer is not None:
                    consumer.close()
            except Exception:
                pass
        if not _stop.wait(2.0):
            continue
        break


def _authorized_frame(msg) -> dict | None:
    from apps.common.framesig import verify_frame
    from apps.inference.remote import ingest_token

    if not isinstance(msg, dict):
        return None
    secret = ingest_token()
    sig = str(msg.get("sig") or "")
    body = dict(msg)
    body.pop("sig", None)
    body.pop("ingestToken", None)
    if not verify_frame(body, secret, sig):
        logger.warning("kafka detect.frames rejected (bad signature)")
        return None
    return body

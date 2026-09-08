"""RabbitMQ job transport: durable queues, ack, retry, dead-letter.

Public names stay evidence / notify / flywheel. Django only publishes;
runtime consumes. Failed jobs after MAX_ATTEMPTS go to the DLQ — never
a Django HTTP thread.
"""
from __future__ import annotations

import json
import logging
import threading
from urllib.parse import urlparse

logger = logging.getLogger("common.mq")

_EXCHANGE = "jobs"
_DLX = "jobs.dlx"
_DLQ = "jobs.dlq"

_pub_lock = threading.Lock()
_pub_conn = None
_pub_ch = None


def _url() -> str:
    from django.conf import settings

    return (getattr(settings, "RABBITMQ_URL", None) or "amqp://admin:admin@127.0.0.1:5672/my_vhost").strip()


def _prefix() -> str:
    from django.conf import settings

    return (getattr(settings, "REDIS_PREFIX", None) or "yolov8").strip() or "yolov8"


def queue_name(logical: str) -> str:
    return f"{_prefix()}.{logical}"


def _params():
    import pika

    parsed = urlparse(_url())
    return pika.ConnectionParameters(
        host=parsed.hostname or "127.0.0.1",
        port=int(parsed.port or 5672),
        virtual_host=parsed.path.lstrip("/") or "/",
        credentials=pika.PlainCredentials(parsed.username or "guest", parsed.password or "guest"),
        heartbeat=30,
        blocked_connection_timeout=10,
        connection_attempts=3,
        retry_delay=1,
        socket_timeout=8,
    )


def declare(channel) -> None:
    import pika

    prefix = _prefix()
    exchange = f"{prefix}.{_EXCHANGE}"
    dlx = f"{prefix}.{_DLX}"
    dlq = f"{prefix}.{_DLQ}"
    channel.exchange_declare(exchange=exchange, exchange_type="direct", durable=True)
    channel.exchange_declare(exchange=dlx, exchange_type="fanout", durable=True)
    channel.queue_declare(queue=dlq, durable=True)
    channel.queue_bind(queue=dlq, exchange=dlx)
    args = {"x-dead-letter-exchange": dlx}
    for logical in ("evidence", "notify", "flywheel"):
        q = queue_name(logical)
        channel.queue_declare(queue=q, durable=True, arguments=args)
        channel.queue_bind(queue=q, exchange=exchange, routing_key=logical)


def _connect():
    import pika

    conn = pika.BlockingConnection(_params())
    ch = conn.channel()
    ch.confirm_delivery()
    declare(ch)
    return conn, ch


def _reset_publisher() -> None:
    global _pub_conn, _pub_ch
    try:
        if _pub_conn and _pub_conn.is_open:
            _pub_conn.close()
    except Exception:
        pass
    _pub_conn = None
    _pub_ch = None


def publish(logical_queue: str, job: dict) -> None:
    """Publish a persistent job. Raises if RabbitMQ is down (no in-process fallback)."""
    import pika

    global _pub_conn, _pub_ch
    body = json.dumps(job, ensure_ascii=False).encode("utf-8")
    props = pika.BasicProperties(content_type="application/json", delivery_mode=2, message_id=str(job.get("id") or ""))
    prefix = _prefix()
    exchange = f"{prefix}.{_EXCHANGE}"
    with _pub_lock:
        last_err = None
        for _ in range(2):
            try:
                if _pub_ch is None or _pub_conn is None or _pub_conn.is_closed or _pub_ch.is_closed:
                    _reset_publisher()
                    _pub_conn, _pub_ch = _connect()
                _pub_ch.basic_publish(
                    exchange=exchange,
                    routing_key=logical_queue,
                    body=body,
                    properties=props,
                    mandatory=False,
                )
                return
            except Exception as exc:
                last_err = exc
                logger.warning("rabbit publish retry queue=%s: %s", logical_queue, exc)
                _reset_publisher()
        raise RuntimeError(f"rabbitmq publish failed queue={logical_queue}: {last_err}")


def publish_dlq(job: dict, reason: str) -> None:
    import pika

    payload = dict(job)
    payload["dlqReason"] = reason
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    conn, ch = _connect()
    try:
        dlq = f"{_prefix()}.{_DLQ}"
        ch.basic_publish(
            exchange="",
            routing_key=dlq,
            body=body,
            properties=pika.BasicProperties(content_type="application/json", delivery_mode=2),
        )
    finally:
        try:
            conn.close()
        except Exception:
            pass


def consume_loop(on_job, should_stop) -> None:
    """Block until should_stop(); each message is acked after on_job returns."""
    import pika

    from apps.common.jobs import QUEUE_EVIDENCE, QUEUE_FLYWHEEL, QUEUE_NOTIFY

    logicals = (QUEUE_EVIDENCE, QUEUE_NOTIFY, QUEUE_FLYWHEEL)
    queues = [queue_name(q) for q in logicals]
    while not should_stop():
        conn = None
        try:
            conn, ch = _connect()
            ch.basic_qos(prefetch_count=1)

            def _cb(channel, method, _props, body, logical=None):
                try:
                    job = json.loads(body.decode("utf-8") if isinstance(body, (bytes, bytearray)) else body)
                    if logical and not job.get("queue"):
                        job["queue"] = logical
                    on_job(job)
                    channel.basic_ack(method.delivery_tag)
                except Exception:
                    logger.exception("rabbit handler crashed; nack without requeue → retry publish")
                    try:
                        channel.basic_nack(method.delivery_tag, requeue=False)
                    except Exception:
                        pass

            for logical, q in zip(logicals, queues):
                ch.basic_consume(queue=q, on_message_callback=lambda c, m, p, b, log=logical: _cb(c, m, p, b, log), auto_ack=False)

            while not should_stop():
                conn.process_data_events(time_limit=1.0)
        except pika.exceptions.AMQPError as exc:
            logger.warning("rabbit consume reconnect: %s", exc)
        except Exception as exc:
            logger.warning("rabbit consume error: %s", exc)
        finally:
            try:
                if conn and conn.is_open:
                    conn.close()
            except Exception:
                pass
        if should_stop():
            break
        if not should_stop():
            import time

            time.sleep(2.0)

"""Task queue: same enqueue() API, RabbitMQ by default (Redis List optional).

Queues:
  evidence  capture_snapshot / capture_clip
  notify    notify.alert
  flywheel  sample / yaml / train

JOBS_SYNC=1 runs handlers inline (tests). Redis-down no longer falls back to
a Django HTTP thread — publish fails and the caller logs it.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid

from django.conf import settings
from django.db import close_old_connections

from apps.common import rdb

logger = logging.getLogger("common.jobs")

QUEUE_EVIDENCE = "evidence"
QUEUE_NOTIFY = "notify"
QUEUE_FLYWHEEL = "flywheel"
_QUEUES = (QUEUE_EVIDENCE, QUEUE_NOTIFY, QUEUE_FLYWHEEL)

_HANDLERS: dict[str, callable] = {}
_stop = threading.Event()
_threads: list[threading.Thread] = []
_handlers_loaded = False
MAX_ATTEMPTS = {
    "capture_snapshot": 2,
    "capture_clip": 2,
    "notify.alert": 3,
    "flywheel.sample": 5,
    "flywheel.yaml": 2,
    "flywheel.train": 1,
}


def register(name: str):
    def deco(fn):
        _HANDLERS[name] = fn
        return fn
    return deco


def jobs_backend() -> str:
    raw = (getattr(settings, "JOBS_BACKEND", None) or "rabbitmq").strip().lower()
    if raw in ("redis", "list", "rdb"):
        return "redis"
    return "rabbitmq"


def _queue_key(name: str) -> str:
    return rdb.prefix("q", name)


def _load_handlers():
    global _handlers_loaded
    if _handlers_loaded:
        return
    from apps.alerts import jobs as _alert_jobs  # noqa: F401
    from apps.inference import notify as _notify  # noqa: F401
    from apps.flywheel import jobs as _flywheel_jobs  # noqa: F401
    _handlers_loaded = True


def run_job(job: dict) -> None:
    _load_handlers()
    name = str(job.get("task") or "")
    handler = _HANDLERS.get(name)
    if handler is None:
        logger.error("unknown job %s", name)
        return
    close_old_connections()
    try:
        handler(job.get("payload") or {})
    finally:
        close_old_connections()


def enqueue(queue: str, task: str, payload: dict | None = None, *, sync: bool | None = None) -> str:
    job = {
        "id": uuid.uuid4().hex,
        "task": task,
        "queue": queue,
        "payload": dict(payload or {}),
        "attempts": 0,
        "ts": time.time(),
    }
    use_sync = settings.JOBS_SYNC if sync is None else sync
    if use_sync:
        run_job(job)
        return job["id"]
    if jobs_backend() == "redis":
        _enqueue_redis(queue, job)
        return job["id"]
    from apps.common import mq

    mq.publish(queue, job)
    return job["id"]


def _enqueue_redis(queue: str, job: dict) -> None:
    client = rdb.get_client()
    if client is None:
        raise RuntimeError("redis job backend unavailable (no Django thread fallback)")
    client.lpush(_queue_key(queue), json.dumps(job, ensure_ascii=False).encode("utf-8"))


def _handle_failure(job: dict, *, delay: float = 0, count_attempt: bool = True, reason: str = "error") -> None:
    if count_attempt:
        job["attempts"] = int(job.get("attempts") or 0) + 1
    name = str(job.get("task") or "")
    limit = MAX_ATTEMPTS.get(name, 2)
    queue = str(job.get("queue") or QUEUE_EVIDENCE)
    if int(job.get("attempts") or 0) >= limit:
        logger.error("job dropped after %s attempts task=%s id=%s", job.get("attempts"), name, job.get("id"))
        if jobs_backend() != "redis":
            try:
                from apps.common import mq

                mq.publish_dlq(job, reason)
            except Exception:
                logger.exception("dlq publish failed task=%s", name)
        return
    if delay > 0:
        time.sleep(min(delay, 8))
    if jobs_backend() == "redis":
        client = rdb.get_client()
        if client is None:
            logger.error("requeue skipped, redis down task=%s", name)
            return
        client.lpush(_queue_key(queue), json.dumps(job, ensure_ascii=False).encode("utf-8"))
        return
    from apps.common import mq

    mq.publish(queue, job)


def _dispatch(job: dict) -> None:
    try:
        run_job(job)
    except Requeue as exc:
        _handle_failure(job, delay=exc.delay, count_attempt=exc.count_attempt, reason="requeue")
    except Exception:
        logger.exception("job failed task=%s id=%s", job.get("task"), job.get("id"))
        _handle_failure(job, delay=1.5, reason="exception")


def _redis_worker_loop(worker_id: int) -> None:
    logger.info("redis job worker %s started", worker_id)
    keys = [_queue_key(q) for q in _QUEUES]
    while not _stop.is_set():
        client = rdb.get_client()
        if client is None:
            if _stop.wait(2.0):
                break
            rdb.get_client(force=True)
            continue
        try:
            item = client.brpop(keys, timeout=2)
        except Exception as exc:
            logger.warning("worker %s brpop failed: %s", worker_id, exc)
            if _stop.wait(1.0):
                break
            continue
        if not item:
            continue
        _queue_bytes, body = item
        try:
            job = json.loads(body.decode("utf-8") if isinstance(body, (bytes, bytearray)) else body)
        except Exception:
            logger.exception("worker %s bad job payload", worker_id)
            continue
        _dispatch(job)
    logger.info("redis job worker %s stopped", worker_id)


def _rabbit_worker_loop(worker_id: int) -> None:
    logger.info("rabbit job worker %s started", worker_id)
    from apps.common import mq

    mq.consume_loop(_dispatch, lambda: _stop.is_set())
    logger.info("rabbit job worker %s stopped", worker_id)


class Requeue(Exception):
    def __init__(self, delay: float = 2.0, *, count_attempt: bool = True):
        super().__init__("requeue")
        self.delay = delay
        self.count_attempt = count_attempt


def start_embedded_workers() -> None:
    global _threads
    if not getattr(settings, "JOBS_EMBEDDED", True):
        return
    if any(t.is_alive() for t in _threads):
        return
    _load_handlers()
    _stop.clear()
    n = int(getattr(settings, "JOBS_WORKERS", 2) or 2)
    backend = jobs_backend()
    target = _rabbit_worker_loop if backend == "rabbitmq" else _redis_worker_loop
    started = []
    for i in range(n):
        t = threading.Thread(target=target, args=(i + 1,), name=f"job-worker-{i + 1}", daemon=True)
        t.start()
        started.append(t)
    _threads = started
    logger.info("embedded job workers=%s backend=%s", n, backend)


def stop_embedded_workers() -> None:
    _stop.set()


def run_forever() -> None:
    """Standalone `manage.py run_jobs` loop (also starts N worker threads)."""
    start_embedded_workers()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_embedded_workers()

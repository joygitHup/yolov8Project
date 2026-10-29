"""Trace ID + Prometheus metrics middleware."""
from __future__ import annotations

import logging
import time
import uuid
from threading import Lock

logger = logging.getLogger("common.trace")

# ---------------------------------------------------------------------------
# In-memory Prometheus-style counters (no external dependency)
# ---------------------------------------------------------------------------
_metrics_lock = Lock()
_counters: dict[str, int] = {}
_gauges: dict[str, float] = {}


def inc_counter(name: str, value: int = 1) -> None:
    with _metrics_lock:
        _counters[name] = _counters.get(name, 0) + value


def set_gauge(name: str, value: float) -> None:
    with _metrics_lock:
        _gauges[name] = float(value)


def snapshot_metrics() -> dict[str, float]:
    """Return a copy of all counters + gauges."""
    with _metrics_lock:
        out: dict[str, float] = {}
        out.update({k: float(v) for k, v in _counters.items()})
        out.update(dict(_gauges))
        return out


# ---------------------------------------------------------------------------
# Trace ID middleware
# ---------------------------------------------------------------------------


class TraceIDMiddleware:
    """
    Attach a unique trace ID to every request. The ID is propagated on the
    request (`request.META["TRACE_ID"]`), echoed back in the response header
    `X-Trace-Id`, and logged with every access line so operators can follow
    a single request across Django → Kafka → yolo-service callbacks.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Prefer client-provided trace id if present; otherwise generate one
        incoming = (request.headers.get("X-Trace-Id") or "").strip()
        trace_id = incoming or uuid.uuid4().hex[:16]
        request.META["TRACE_ID"] = trace_id

        start = time.perf_counter()
        try:
            response = self.get_response(request)
        except Exception as exc:
            logger.exception("[trace=%s] %s %s raised %s", trace_id, request.method, request.path, exc)
            raise
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        response["X-Trace-Id"] = trace_id
        logger.info(
            "[trace=%s] %s %s -> %s (%.1fms)",
            trace_id,
            request.method,
            request.path,
            response.status_code,
            elapsed_ms,
        )

        # Update Prometheus-style metrics
        inc_counter("http_requests_total")
        inc_counter(f"http_requests_status_{response.status_code}")
        # Bucketized latency (ms) as histogram-like counters
        if elapsed_ms < 100:
            inc_counter("http_requests_latency_lt_100ms")
        elif elapsed_ms < 500:
            inc_counter("http_requests_latency_lt_500ms")
        elif elapsed_ms < 2000:
            inc_counter("http_requests_latency_lt_2000ms")
        else:
            inc_counter("http_requests_latency_gte_2000ms")

        return response

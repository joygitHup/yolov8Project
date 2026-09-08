"""Redis helpers: dedup, cooldown, last-frame cache, stream health.

Uses the Docker Redis on :6379 and logical DB from REDIS_URL (default /2).
Cross-process state (API vs runtime) never falls back to in-memory dicts —
that split-brain duplicates alerts and hides missing frames. Memory fallback
only when Django embeds runtime in one process.
"""
from __future__ import annotations

import json
import logging
import threading
import time

from django.conf import settings

logger = logging.getLogger("common.rdb")

_client = None
_client_failed = False
_client_failed_at = 0.0
_REDIS_RETRY_SEC = 5.0
_lock = threading.Lock()
_STREAM_STALE_SEC = 30.0
_mem_dedup: dict[str, float] = {}
_mem_cooldown: dict[int, float] = {}
_mem_quota: dict[str, int] = {}
_mem_gap: dict[int, float] = {}
_mem_clip: dict[int, float] = {}
_mem_frame: dict[int, tuple[float, bytes]] = {}
_FRAME_TTL = 30
_CLIP_RING = 24
_mem_clip_ring: dict[int, list[bytes]] = {}


def prefix(*parts) -> str:
    head = (getattr(settings, "REDIS_PREFIX", None) or "yolov8").strip() or "yolov8"
    return head + ":" + ":".join(str(p) for p in parts)


def allow_memory() -> bool:
    """In-process dicts are only safe when API and runtime share one process."""
    try:
        from apps.common.process import django_embeds_runtime

        return django_embeds_runtime()
    except Exception:
        return False


def get_client(force: bool = False):
    """Return a redis.Redis client or None if Redis is down."""
    global _client, _client_failed, _client_failed_at
    if _client is not None and not force:
        return _client
    if _client_failed and not force:
        if time.time() - _client_failed_at < _REDIS_RETRY_SEC:
            return None
    with _lock:
        if _client is not None and not force:
            return _client
        if _client_failed and not force and time.time() - _client_failed_at < _REDIS_RETRY_SEC:
            return None
        try:
            import redis as redis_lib

            url = getattr(settings, "REDIS_URL", "redis://127.0.0.1:6379/2")
            client = redis_lib.Redis.from_url(
                url,
                decode_responses=False,
                socket_connect_timeout=2,
                socket_timeout=15,
                health_check_interval=30,
            )
            client.ping()
            _client = client
            _client_failed = False
            logger.info("redis connected %s", url)
            return _client
        except Exception as exc:
            _client = None
            _client_failed = True
            _client_failed_at = time.time()
            logger.warning("redis unavailable: %s", exc)
            return None


def ping() -> bool:
    global _client_failed
    client = get_client(force=_client_failed)
    if client is None:
        return False
    try:
        return bool(client.ping())
    except Exception:
        _client_failed = True
        _client_failed_at = time.time()
        return False


def try_dedup(camera_id: int, alert_type: str, interval: int) -> bool:
    """Return True if this alert should be dropped (duplicate within interval)."""
    ttl = max(1, int(interval or 30))
    key = prefix("dedup", int(camera_id), alert_type)
    client = get_client()
    if client is not None:
        try:
            ok = client.set(key, b"1", nx=True, ex=ttl)
            return not bool(ok)
        except Exception as exc:
            logger.warning("redis dedup failed: %s", exc)
    if allow_memory():
        now = time.time()
        last = _mem_dedup.get(key)
        if last and now - last < ttl:
            return True
        _mem_dedup[key] = now
        return False
    logger.error("dedup skipped, redis down camera=%s type=%s", camera_id, alert_type)
    return True


def on_cooldown(camera_id: int) -> bool:
    cid = int(camera_id)
    client = get_client()
    if client is not None:
        try:
            return bool(client.exists(prefix("cooldown", cid)))
        except Exception as exc:
            logger.warning("redis cooldown read failed: %s", exc)
    if allow_memory():
        return time.time() < _mem_cooldown.get(cid, 0)
    return False


def put_cooldown(camera_id: int, sec: float) -> None:
    cid = int(camera_id)
    ttl = max(1, int(sec or 60))
    client = get_client()
    if client is not None:
        try:
            client.setex(prefix("cooldown", cid), ttl, b"1")
            return
        except Exception as exc:
            logger.warning("redis cooldown write failed: %s", exc)
    if allow_memory():
        _mem_cooldown[cid] = time.time() + ttl


def clear_cooldown(camera_id: int) -> None:
    cid = int(camera_id)
    client = get_client()
    if client is not None:
        try:
            client.delete(prefix("cooldown", cid))
        except Exception:
            pass
    _mem_cooldown.pop(cid, None)


def put_last_frame_jpeg(camera_id: int, jpeg: bytes, ttl: int = 30) -> bool:
    if not jpeg:
        return False
    cid = int(camera_id)
    client = get_client()
    if client is None:
        if allow_memory():
            _mem_frame[cid] = (time.time(), jpeg)
            return True
        return False
    try:
        client.setex(prefix("frame", cid), max(2, int(ttl or _FRAME_TTL)), jpeg)
        return True
    except Exception as exc:
        logger.warning("redis last-frame write failed: %s", exc)
        if allow_memory():
            _mem_frame[cid] = (time.time(), jpeg)
            return True
        return False


def push_clip_jpeg(camera_id: int, jpeg: bytes, maxlen: int = _CLIP_RING) -> None:
    del camera_id, jpeg, maxlen


def get_clip_jpegs(camera_id: int) -> list[bytes]:
    del camera_id
    return []


def put_last_frame_bgr(camera_id: int, frame, ttl: int = 30) -> bool:
    if frame is None:
        return False
    try:
        import cv2

        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        if not ok:
            return False
        return put_last_frame_jpeg(camera_id, buf.tobytes(), ttl)
    except Exception as exc:
        logger.warning("last-frame encode failed: %s", exc)
        return False


def has_last_frame_jpeg(camera_id: int) -> bool:
    """True when a last-frame JPEG exists — does not download the blob."""
    cid = int(camera_id)
    client = get_client()
    if client is not None:
        try:
            return bool(client.exists(prefix("frame", cid)))
        except Exception as exc:
            logger.warning("redis last-frame exists failed: %s", exc)
    if allow_memory():
        item = _mem_frame.get(cid)
        return bool(item and time.time() - item[0] <= _FRAME_TTL)
    return False


def get_last_frame_jpeg(camera_id: int) -> bytes | None:
    cid = int(camera_id)
    client = get_client()
    if client is not None:
        try:
            data = client.get(prefix("frame", cid))
            if data:
                return data
        except Exception as exc:
            logger.warning("redis last-frame read failed: %s", exc)
    if allow_memory():
        item = _mem_frame.get(cid)
        if item and time.time() - item[0] <= _FRAME_TTL:
            return item[1]
    return None


def put_last_frame_meta(camera_id: int, frame: dict, ttl: int = 30) -> None:
    """Share detection boxes across API / runtime processes."""
    import json

    if not isinstance(frame, dict):
        return
    cid = int(camera_id)
    raw = json.dumps(frame, ensure_ascii=False).encode("utf-8")
    client = get_client()
    if client is None:
        return
    try:
        client.setex(prefix("frame", "meta", cid), max(2, int(ttl or _FRAME_TTL)), raw)
    except Exception as exc:
        logger.warning("redis frame-meta write failed: %s", exc)


def get_last_frame_meta(camera_id: int) -> dict | None:
    import json

    cid = int(camera_id)
    client = get_client()
    if client is None:
        return None
    try:
        data = client.get(prefix("frame", "meta", cid))
        if not data:
            return None
        obj = json.loads(data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else data)
        return obj if isinstance(obj, dict) else None
    except Exception as exc:
        logger.warning("redis frame-meta read failed: %s", exc)
        return None


def get_last_frame_metas(camera_ids) -> dict[int, dict]:
    ids = [int(i) for i in (camera_ids or [])]
    client = get_client()
    if client is None or not ids:
        return {}
    try:
        keys = [prefix("frame", "meta", cid) for cid in ids]
        raws = client.mget(keys)
    except Exception as exc:
        logger.warning("redis frame-meta mget failed: %s", exc)
        return {}
    out: dict[int, dict] = {}
    for cid, raw in zip(ids, raws or []):
        obj = _decode_json(raw)
        if obj:
            out[cid] = obj
    return out


def get_last_frame_bgr(camera_id: int):
    data = get_last_frame_jpeg(camera_id)
    if not data:
        return None
    try:
        import cv2
        import numpy as np

        arr = np.frombuffer(data, dtype=np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)
    except Exception as exc:
        logger.warning("last-frame decode failed: %s", exc)
        return None


def flywheel_allow(camera_id: int, interval_sec: int, hourly_quota: int, *, force: bool = False) -> bool:
    """Rate-limit flywheel sampling. force=True (alert frames) always accepts but still counts."""
    cid = int(camera_id)
    interval = max(0, int(interval_sec or 0))
    quota = max(1, int(hourly_quota or 40))
    hour = time.strftime("%Y%m%d%H")
    quota_key = prefix("flywheel", "quota", cid, hour)
    gap_key = prefix("flywheel", "gap", cid)
    client = get_client()

    if not force and interval > 0:
        if client is not None:
            try:
                if not client.set(gap_key, b"1", nx=True, ex=interval):
                    return False
            except Exception as exc:
                logger.warning("flywheel gap redis failed: %s", exc)
        else:
            if allow_memory():
                now = time.time()
                if now < _mem_gap.get(cid, 0):
                    return False
                _mem_gap[cid] = now + interval
            else:
                return False

    if client is not None:
        try:
            n = int(client.incr(quota_key))
            if n == 1:
                client.expire(quota_key, 7200)
            if force:
                return True
            return n <= quota
        except Exception as exc:
            logger.warning("flywheel quota redis failed: %s", exc)

    if not allow_memory():
        return False
    qk = f"{cid}:{hour}"
    _mem_quota[qk] = int(_mem_quota.get(qk, 0)) + 1
    if force:
        return True
    return _mem_quota[qk] <= quota


def acquire_clip_lock(camera_id: int, ttl: int = 25) -> bool:
    cid = int(camera_id)
    client = get_client()
    if client is not None:
        try:
            return bool(client.set(prefix("clip", "lock", cid), b"1", nx=True, ex=max(5, int(ttl))))
        except Exception as exc:
            logger.warning("redis clip lock failed: %s", exc)
    if not allow_memory():
        return False
    now = time.time()
    until = _mem_clip.get(cid, 0)
    if now < until:
        return False
    _mem_clip[cid] = now + max(5, int(ttl))
    return True


def release_clip_lock(camera_id: int) -> None:
    cid = int(camera_id)
    client = get_client()
    if client is not None:
        try:
            client.delete(prefix("clip", "lock", cid))
        except Exception:
            pass
    _mem_clip.pop(cid, None)


def _decode_json(raw) -> dict | None:
    if not raw:
        return None
    try:
        obj = json.loads(raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _fresh(payload: dict | None) -> dict | None:
    if not payload:
        return None
    try:
        ts = float(payload.get("ts") or 0)
    except (TypeError, ValueError):
        return None
    if ts <= 0 or time.time() - ts > _STREAM_STALE_SEC:
        return None
    return payload


def put_stream_health(camera_id: int, data: dict) -> None:
    cid = int(camera_id)
    payload = dict(data or {})
    payload["cameraId"] = cid
    payload["ts"] = time.time()
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    client = get_client()
    if client is None:
        return
    try:
        pipe = client.pipeline()
        pipe.setex(prefix("stream", cid), 45, raw)
        pipe.hset(prefix("stream", "all"), str(cid), raw)
        pipe.execute()
    except Exception as exc:
        logger.warning("stream health write failed camera=%s: %s", cid, exc)


def get_stream_health(camera_id: int) -> dict | None:
    client = get_client()
    if client is None:
        return None
    try:
        return _fresh(_decode_json(client.get(prefix("stream", int(camera_id)))))
    except Exception as exc:
        logger.warning("stream health read failed camera=%s: %s", camera_id, exc)
        return None


def get_all_stream_health() -> dict[int, dict]:
    client = get_client()
    if client is None:
        return {}
    try:
        items = client.hgetall(prefix("stream", "all")) or {}
    except Exception as exc:
        logger.warning("stream health dump failed: %s", exc)
        return {}
    out: dict[int, dict] = {}
    for key, raw in items.items():
        try:
            cid = int(key.decode("utf-8") if isinstance(key, (bytes, bytearray)) else key)
        except (TypeError, ValueError):
            continue
        payload = _fresh(_decode_json(raw))
        if payload:
            out[cid] = payload
    return out


def put_stream_cmd(camera_id: int, action: str) -> None:
    act = (action or "").strip().lower()
    if act not in ("start", "stop"):
        return
    client = get_client()
    if client is None:
        raise RuntimeError("Redis 不可用，无法通知 runtime 启停预览")
    client.hset(prefix("stream", "cmd"), str(int(camera_id)), act.encode("utf-8"))


def pop_stream_cmds() -> list[tuple[int, str]]:
    client = get_client()
    if client is None:
        return []
    key = prefix("stream", "cmd")
    try:
        items = client.hgetall(key) or {}
        if items:
            client.delete(key)
    except Exception as exc:
        logger.warning("stream cmd read failed: %s", exc)
        return []
    out = []
    for k, v in items.items():
        try:
            cid = int(k.decode("utf-8") if isinstance(k, (bytes, bytearray)) else k)
        except (TypeError, ValueError):
            continue
        act = (v.decode("utf-8") if isinstance(v, (bytes, bytearray)) else str(v)).strip().lower()
        if act in ("start", "stop"):
            out.append((cid, act))
    return out

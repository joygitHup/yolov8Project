"""Standalone runtime: YOLO orchestrator + job workers + demo RTSP publish."""
from __future__ import annotations

import logging
import threading
import time

from django.conf import settings

logger = logging.getLogger("runtime")

_stop = threading.Event()


def start_runtime() -> None:
    """Start background work that must not live in the API process."""
    from apps.common.process import enable_sqlite_wal

    enable_sqlite_wal()
    settings.JOBS_EMBEDDED = True
    from apps.common.jobs import start_embedded_workers
    from apps.common.storage import ping as minio_ping
    from apps.inference.pipeline import start_pipeline
    from apps.streaming.manager import stream_manager
    from apps.streaming.publisher import demo_publish_enabled, demo_publisher, wire_cameras_to_demo_rtsp

    status = minio_ping()
    print(
        f"[runtime] evidence backend={status.get('backend')} minio_ok={status.get('ok')}",
        flush=True,
    )
    try:
        updated, total = wire_cameras_to_demo_rtsp()
        ok = demo_publisher.ensure_started()
        mode = "on" if ok else ("off" if not demo_publish_enabled() else "off (fallback)")
        logger.info("demo RTSP cameras=%s/%s publisher=%s", updated, total, mode)
    except Exception:
        logger.exception("demo RTSP bootstrap failed")
    try:
        n = stream_manager.ensure_online_cameras()
        logger.info("preview streams ready=%s", n)
    except Exception:
        logger.exception("ensure preview streams failed")
    start_embedded_workers()
    start_pipeline()
    try:
        from apps.common import bus
        from apps.inference.pipeline import ingest_detections

        def _on_detect(msg: dict) -> None:
            camera_id = int(msg.get("cameraId") or 0)
            if not camera_id:
                return
            detections = msg.get("detections") if isinstance(msg.get("detections"), list) else []
            meta = {
                "timestamp": msg.get("timestamp"),
                "fps": msg.get("fps"),
                "modelReady": msg.get("modelReady", True),
                "inferActive": msg.get("inferActive", True),
            }
            ingest_detections(camera_id, detections, meta)

        bus.start_frames_consumer(_on_detect)
        print("[runtime] kafka consumer detect.frames", flush=True)
    except Exception:
        logger.exception("kafka detect.frames consumer failed to start")
    threading.Thread(target=_preview_loop, name="preview-ensure", daemon=True).start()
    print("[runtime] started (pipeline + jobs + streaming)", flush=True)
    logger.info("runtime started (pipeline + jobs + streaming)")


def _preview_loop() -> None:
    from apps.streaming.manager import stream_manager
    from apps.streaming.publisher import demo_publisher

    ticks = 0
    while not _stop.wait(2.0):
        ticks += 1
        try:
            stream_manager.process_stream_cmds()
            if ticks == 1 or ticks % 6 == 0:
                demo_publisher.ensure_started()
                stream_manager.ensure_online_cameras()
        except Exception:
            logger.exception("preview ensure loop failed")


def stop_runtime() -> None:
    _stop.set()
    try:
        from apps.inference.pipeline import stop_pipeline

        stop_pipeline()
    except Exception:
        logger.exception("stop pipeline failed")
    try:
        from apps.common.jobs import stop_embedded_workers

        stop_embedded_workers()
    except Exception:
        pass
    try:
        from apps.common.bus import stop_consumers

        stop_consumers()
    except Exception:
        pass
    try:
        from apps.streaming.manager import stream_manager

        stream_manager.stop_all()
    except Exception:
        pass
    try:
        from apps.streaming.publisher import demo_publisher

        demo_publisher.stop()
    except Exception:
        pass


def run_forever() -> None:
    start_runtime()
    try:
        while not _stop.wait(1.0):
            time.sleep(0)
    except KeyboardInterrupt:
        pass
    finally:
        stop_runtime()

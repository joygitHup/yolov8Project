"""RTSP workers: grab -> predict -> HTTP callback. Same RTSP shares one infer loop."""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app import engine, frames
from app.schemas import CameraStatus, StartCameraRequest

logger = logging.getLogger("yolo.worker")

_DEFAULT_TOKEN = os.environ.get("INGEST_TOKEN", "").strip()
_GRAB_FAIL_LIMIT = 8
_GRAB_BACKOFF_SEC = 30.0


def _callback(
    callback_url: str,
    ingest_token: str,
    payload: dict,
) -> tuple[bool, str]:
    if not callback_url:
        return True, ""
    headers = {"Content-Type": "application/json"}
    if ingest_token:
        headers["X-Ingest-Token"] = ingest_token
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.post(callback_url, json=payload, headers=headers)
        if resp.status_code >= 400:
            return False, f"callback HTTP {resp.status_code}"
        return True, ""
    except Exception as exc:
        return False, f"callback: {exc}"


def _emit(slot: "CameraSlot", payload: dict) -> tuple[bool, str]:
    """Kafka first (no JPEG). HTTP ingest only if Kafka is down."""
    from app import bus

    if bus.produce_frame(payload):
        return True, ""
    light = dict(payload)
    light.pop("frameJpeg", None)
    return _callback(slot.callback_url, slot.ingest_token, light)


class CameraSlot:
    """Per-camera callback / params attached to a shared RTSP stream."""

    def __init__(self, req: StartCameraRequest):
        self.camera_id = int(req.cameraId)
        self.rtsp = (req.rtsp or "").strip()
        self.conf = float(req.conf)
        self.iou = float(req.iou)
        self.max_det = int(req.maxDet)
        self.fps = max(0.5, min(float(req.fps or 1), 2.0))
        self.model_path = req.modelPath
        self.callback_url = (req.callbackUrl or "").strip()
        self.ingest_token = (req.ingestToken or _DEFAULT_TOKEN or "").strip()
        self.status = "idle"
        self.error = ""
        self.last_callback_ok = False
        self._fail_streak = 0

    def to_status(self, shared_with: list[int] | None = None) -> CameraStatus:
        return CameraStatus(
            cameraId=self.camera_id,
            rtsp=self.rtsp,
            status=self.status,
            fps=self.fps,
            conf=self.conf,
            error=self.error,
            lastCallbackOk=self.last_callback_ok,
            shared=bool(shared_with and len(shared_with) > 1),
            sharedWith=shared_with or [],
        )

    def apply(self, req: StartCameraRequest) -> None:
        self.rtsp = (req.rtsp or "").strip()
        self.conf = float(req.conf)
        self.iou = float(req.iou)
        self.max_det = int(req.maxDet)
        self.fps = max(0.5, min(float(req.fps or 1), 2.0))
        self.model_path = req.modelPath
        self.callback_url = (req.callbackUrl or "").strip()
        self.ingest_token = (req.ingestToken or _DEFAULT_TOKEN or "").strip()


class SharedRtspWorker:
    """One grab + one predict per tick; fan-out callbacks to all camera slots."""

    def __init__(self, rtsp: str):
        self.rtsp = rtsp
        self._slots: dict[int, CameraSlot] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._grab_fail = 0

    def slot_ids(self) -> list[int]:
        with self._lock:
            return list(self._slots.keys())

    def has_slots(self) -> bool:
        with self._lock:
            return bool(self._slots)

    def upsert(self, slot: CameraSlot) -> None:
        with self._lock:
            self._slots[slot.camera_id] = slot
            slot.status = "running"
            slot.error = ""
        self._ensure_thread()

    def remove(self, camera_id: int) -> CameraSlot | None:
        with self._lock:
            slot = self._slots.pop(int(camera_id), None)
        if slot:
            slot.status = "idle"
            frames.release_camera(slot.camera_id)
        return slot

    def list_statuses(self) -> list[CameraStatus]:
        with self._lock:
            ids = list(self._slots.keys())
            return [s.to_status(ids) for s in self._slots.values()]

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        with self._lock:
            slots = list(self._slots.values())
            self._slots.clear()
        for slot in slots:
            frames.release_camera(slot.camera_id)
            slot.status = "idle"

    def _ensure_thread(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name=f"yolo-rtsp-{abs(hash(self.rtsp)) % 10_000_000}",
            daemon=True,
        )
        self._thread.start()

    def _params(self) -> tuple[float, float, float, int, str | None]:
        """Aggregate fps/conf/iou/max_det/model across slots."""
        with self._lock:
            slots = list(self._slots.values())
        if not slots:
            return 1.0, 0.5, 0.45, 100, None
        fps = max(s.fps for s in slots)
        conf = min(s.conf for s in slots)
        iou = slots[0].iou
        max_det = max(s.max_det for s in slots)
        model_path = next((s.model_path for s in slots if s.model_path), None)
        return fps, conf, iou, max_det, model_path

    def _loop(self) -> None:
        logger.info("shared worker start rtsp=%s", self.rtsp)
        while not self._stop.wait(0):
            if not self.has_slots():
                break
            fps, conf, iou, max_det, model_path = self._params()
            interval = max(0.5, 1.0 / fps)
            t0 = time.time()
            try:
                # Use first camera id as grab key; frames module shares by URL.
                with self._lock:
                    primary_id = next(iter(self._slots))
                frame = frames.grab_frame(primary_id, self.rtsp)
                detections: list[dict[str, Any]] = []
                if frame is not None:
                    self._grab_fail = 0
                    detections = engine.predict(
                        frame,
                        conf=conf,
                        iou=iou,
                        max_det=max_det,
                        model_path=model_path,
                    )
                if frame is not None:
                    try:
                        import cv2
                        from app import framecache

                        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
                        if ok:
                            jpeg = buf.tobytes()
                            with self._lock:
                                slot_ids = [s.camera_id for s in self._slots.values()]
                            for sid in slot_ids:
                                framecache.put_jpeg(sid, jpeg)
                    except Exception:
                        logger.debug("frame jpeg encode failed", exc_info=True)
                    with self._lock:
                        for slot in self._slots.values():
                            if slot.status == "error" and not slot.error.startswith("callback"):
                                slot.status = "running"
                                slot.error = ""
                else:
                    self._grab_fail += 1
                    err = frames.last_error(primary_id) or "no frame"
                    with self._lock:
                        for slot in self._slots.values():
                            slot.error = err
                            if self._grab_fail >= _GRAB_FAIL_LIMIT:
                                slot.status = "error"
                    if self._grab_fail >= _GRAB_FAIL_LIMIT:
                        logger.warning(
                            "shared worker rtsp unreachable (backoff %.0fs): %s — %s",
                            _GRAB_BACKOFF_SEC,
                            self.rtsp,
                            err,
                        )
                        if self._stop.wait(_GRAB_BACKOFF_SEC):
                            break
                        continue

                ts = datetime.now(timezone.utc).isoformat()
                ready = engine.is_ready()
                with self._lock:
                    slots = list(self._slots.values())
                for slot in slots:
                    payload = {
                        "cameraId": slot.camera_id,
                        "timestamp": ts,
                        "fps": slot.fps,
                        "detections": detections,
                        "modelReady": ready,
                        "inferActive": True,
                    }
                    ok, cerr = _emit(slot, payload)
                    if ok:
                        slot._fail_streak = 0
                        slot.last_callback_ok = True
                        if slot.status == "error" and slot.error.startswith("callback"):
                            slot.status = "running"
                            slot.error = ""
                    else:
                        slot._fail_streak += 1
                        slot.last_callback_ok = False
                        slot.error = cerr
                        if slot._fail_streak >= 5:
                            slot.status = "error"
            except Exception as exc:
                logger.exception("shared worker failed rtsp=%s", self.rtsp)
                with self._lock:
                    for slot in self._slots.values():
                        slot.error = str(exc)
                        slot.status = "error"

            elapsed = time.time() - t0
            wait = max(0.05, interval - elapsed)
            if self._stop.wait(wait):
                break
        logger.info("shared worker stop rtsp=%s", self.rtsp)


class WorkerManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._by_camera: dict[int, str] = {}  # camera_id -> rtsp
        self._by_rtsp: dict[str, SharedRtspWorker] = {}

    def start_camera(self, req: StartCameraRequest) -> CameraStatus:
        cid = int(req.cameraId)
        rtsp = (req.rtsp or "").strip()
        slot = CameraSlot(req)
        with self._lock:
            old_rtsp = self._by_camera.get(cid)
            if old_rtsp and old_rtsp != rtsp:
                old_worker = self._by_rtsp.get(old_rtsp)
                if old_worker:
                    old_worker.remove(cid)
                    if not old_worker.has_slots():
                        old_worker.stop()
                        self._by_rtsp.pop(old_rtsp, None)
            worker = self._by_rtsp.get(rtsp)
            if worker is None:
                worker = SharedRtspWorker(rtsp)
                self._by_rtsp[rtsp] = worker
            worker.upsert(slot)
            self._by_camera[cid] = rtsp
            ids = worker.slot_ids()
        logger.info(
            "camera=%s attached rtsp=%s shared=%s peers=%s",
            cid,
            rtsp,
            len(ids) > 1,
            ids,
        )
        return slot.to_status(ids)

    def stop_camera(self, camera_id: int) -> CameraStatus | None:
        cid = int(camera_id)
        with self._lock:
            rtsp = self._by_camera.pop(cid, None)
            if not rtsp:
                return None
            worker = self._by_rtsp.get(rtsp)
            if not worker:
                return None
            slot = worker.remove(cid)
            if not worker.has_slots():
                worker.stop()
                self._by_rtsp.pop(rtsp, None)
        return slot.to_status() if slot else None

    def stop_all(self) -> int:
        with self._lock:
            workers = list(self._by_rtsp.values())
            n = len(self._by_camera)
            self._by_rtsp.clear()
            self._by_camera.clear()
        for worker in workers:
            worker.stop()
        frames.release_all()
        return n

    def list_cameras(self) -> list[CameraStatus]:
        with self._lock:
            out: list[CameraStatus] = []
            for worker in self._by_rtsp.values():
                out.extend(worker.list_statuses())
            return out

    def count(self) -> int:
        with self._lock:
            return len(self._by_camera)


manager = WorkerManager()

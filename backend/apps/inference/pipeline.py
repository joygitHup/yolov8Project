import logging
import os
import random
import threading

from django.db import close_old_connections
from django.utils import timezone

from apps.alerts.models import Alert
from apps.alerts.serializers import AlertSerializer
from apps.cameras.models import Camera
from apps.common import rdb
from apps.inference import frame_source, remote, yolo_engine
from apps.inference.metrics import flush_metrics, record_frame
from apps.inference.notify import dispatch
from apps.inference.runtime import set_frame
from apps.inference.strategy import allowed_alert_types, match_strategy, should_infer
from apps.realtime.broadcast import broadcast
from apps.systemcfg.defaults import DEFAULT_LABEL_TYPE_MAP
from apps.systemcfg.services import get_section

logger = logging.getLogger("inference")

_TYPE_DESC = {
    "intrusion": "检测到人员进入警戒区域或乱扔垃圾",
    "parking": "禁停区域发现车辆滞留或违停",
    "fire": "检测到明火或烟雾",
}
_stop = threading.Event()
_thread = None
_tracks = {}
_next_track_id = 1
_warned_no_model = False
_rr_index = 0
_remote_started: set[int] = set()
_remote_model_path: str | None = None
_model_ready_cache = False
_COOLDOWN_SEC = 60.0
_UNREACHABLE_HINTS = (
    "cannot open",
    "reconnect failed",
)



def _label_type_map(params):
    raw = params.get("labelTypeMap") if isinstance(params, dict) else None
    if isinstance(raw, dict) and raw:
        return {str(k): str(v) for k, v in raw.items()}
    return dict(DEFAULT_LABEL_TYPE_MAP)


def _alert_type_for_label(label, params):
    mapping = _label_type_map(params)
    if label in mapping:
        return mapping[label]
    lower = {str(k).lower(): v for k, v in mapping.items()}
    return lower.get(str(label).lower())


def _iou(a, b):
    x1 = max(a["x"], b["x"])
    y1 = max(a["y"], b["y"])
    x2 = min(a["x"] + a["w"], b["x"] + b["w"])
    y2 = min(a["y"] + a["h"], b["y"] + b["h"])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    union = a["w"] * a["h"] + b["w"] * b["h"] - inter
    return 0 if union <= 0 else inter / union


def _nms(boxes, threshold):
    ordered = sorted(boxes, key=lambda x: x["confidence"], reverse=True)
    kept = []
    for box in ordered:
        if all(_iou(box, k) < threshold for k in kept):
            kept.append(box)
    return kept


def _mock_infer(params):
    categories = params.get("categories") or []
    if not categories:
        return []
    max_det = int(params.get("maxDetections") or 100)
    conf_min = float(params.get("confidenceThreshold") or 0.5)
    iou_thr = float(params.get("iouThreshold") or 0.45)
    raw = []
    for i in range(random.randint(0, min(3, max_det))):
        raw.append({
            "id": i,
            "label": random.choice(categories),
            "confidence": round(0.35 + random.random() * 0.6, 2),
            "bbox": {
                "x": round(random.random() * 0.8, 4),
                "y": round(random.random() * 0.7, 4),
                "w": round(0.1 + random.random() * 0.2, 4),
                "h": round(0.15 + random.random() * 0.25, 4),
            },
        })
    filtered = [d for d in raw if d["confidence"] >= conf_min]
    boxes = [
        {
            "x": d["bbox"]["x"],
            "y": d["bbox"]["y"],
            "w": d["bbox"]["w"],
            "h": d["bbox"]["h"],
            "confidence": d["confidence"],
            "label": d["label"],
        }
        for d in filtered
    ]
    kept = _nms(boxes, iou_thr)[:max_det]
    return [
        {
            "id": i,
            "label": b["label"],
            "confidence": b["confidence"],
            "bbox": {"x": b["x"], "y": b["y"], "w": b["w"], "h": b["h"]},
        }
        for i, b in enumerate(kept)
    ]


def _yolo_enabled(params) -> bool:
    env = os.environ.get("YOLO_INFER_ENABLED", "1").strip().lower()
    if env in ("0", "false", "no", "off"):
        return False
    return bool(params.get("inferEnabled", True))


def infer_frame(camera, params, frame=None):
    """Local-mode detection (in-process YOLO)."""
    global _warned_no_model
    conf_min = float(params.get("confidenceThreshold") or 0.5)
    iou_thr = float(params.get("iouThreshold") or 0.45)
    max_det = int(params.get("maxDetections") or 100)
    categories = {str(c) for c in (params.get("categories") or [])}

    use_yolo = _yolo_enabled(params)
    detections = []

    if use_yolo:
        model_path = params.get("modelPath")
        if frame is None:
            frame = frame_source.grab_frame(camera.id, camera.rtsp or "")
        if frame is not None:
            detections = yolo_engine.predict(
                frame,
                conf=conf_min,
                iou=iou_thr,
                max_det=max_det,
                model_path=model_path,
            )
            if detections:
                rdb.put_last_frame_bgr(camera.id, frame)
        elif not yolo_engine.is_ready() and yolo_engine.get_load_error():
            if not _warned_no_model:
                logger.warning("YOLO unavailable (%s); using empty detections", yolo_engine.get_load_error())
                _warned_no_model = True
    else:
        detections = _mock_infer(params)

    if categories and detections:
        filtered = [d for d in detections if d.get("label") in categories]
        if filtered or all(d.get("label") in categories for d in detections):
            detections = filtered
        elif not any(d.get("label") in categories for d in detections):
            logger.debug(
                "categories %s have no overlap with model labels; skipping category filter",
                list(categories)[:8],
            )
        else:
            detections = filtered

    for det in detections:
        det["alertType"] = _alert_type_for_label(det.get("label"), params)

    return detections


def filter_by_strategy(camera, detections, params):
    allowed = allowed_alert_types(camera)
    if not allowed:
        return []
    kept = []
    for det in detections:
        alert_type = det.get("alertType") or _alert_type_for_label(det.get("label"), params)
        if alert_type and alert_type in allowed:
            det["alertType"] = alert_type
            kept.append(det)
    return kept


def apply_tracking(camera_id, detections, params):
    global _next_track_id
    if not params.get("trackingEnabled", True):
        return detections
    max_lost = int(params.get("trackLostFrames") or 30)
    state = _tracks.setdefault(int(camera_id), {})
    for track in state.values():
        track["lost"] += 1
    assigned = set()
    for det in detections:
        bbox = det.get("bbox") or {}
        best_id, best_iou = None, 0.3
        for tid, track in state.items():
            if tid in assigned:
                continue
            score = _iou(bbox, track["bbox"])
            if score > best_iou:
                best_id, best_iou = tid, score
        if best_id is not None:
            det["trackId"] = best_id
            state[best_id] = {"bbox": bbox, "lost": 0}
            assigned.add(best_id)
        else:
            tid = _next_track_id
            _next_track_id += 1
            det["trackId"] = tid
            state[tid] = {"bbox": bbox, "lost": 0}
            assigned.add(tid)
    _tracks[int(camera_id)] = {tid: item for tid, item in state.items() if item["lost"] <= max_lost}
    return detections


def _deduped(camera_id, alert_type):
    settings = get_section("alertDeduplication") or {"enabled": True, "interval": 30}
    if not settings.get("enabled", True):
        return False
    interval = int(settings.get("interval") or 30)
    return rdb.try_dedup(camera_id, alert_type, interval)


def _maybe_alert(camera, detections, params=None):
    params = params or get_section("detection")
    grouped = {}
    for det in detections:
        alert_type = det.get("alertType") or _alert_type_for_label(det.get("label"), params)
        if not alert_type:
            continue
        if alert_type not in (camera.detection_types or []):
            continue
        grouped.setdefault(alert_type, []).append(det)
    for alert_type, boxes in grouped.items():
        strategy = match_strategy(camera, alert_type)
        if not strategy or _deduped(camera.id, alert_type):
            continue
        best = max(boxes, key=lambda x: x["confidence"])
        level = "high" if alert_type == "fire" else (strategy.alert_level or "medium")
        alert = Alert.objects.create(
            camera=camera,
            camera_name=camera.name,
            type=alert_type,
            level=level,
            description=_TYPE_DESC.get(alert_type, "检测到异常目标"),
            status="unhandled",
            confidence=best["confidence"],
            snapshot_url="",
            image_url="",
            video_url="",
            detection_boxes=[
                {
                    "x": b["bbox"]["x"],
                    "y": b["bbox"]["y"],
                    "w": b["bbox"]["w"],
                    "h": b["bbox"]["h"],
                    "label": b["label"],
                    "confidence": b["confidence"],
                }
                for b in boxes
            ],
            triggered_at=timezone.now(),
        )
        try:
            from apps.alerts.jobs import enqueue_evidence

            enqueue_evidence(
                alert.id,
                camera.rtsp or "",
                alert.detection_boxes,
                camera_id=camera.id,
            )
        except Exception:
            logger.exception("alert evidence enqueue failed id=%s", alert.id)
        payload = AlertSerializer(alert).data
        broadcast("alert:created", payload)
        try:
            from apps.common import bus

            if bus.enabled():
                bus.produce_alert(payload)
        except Exception:
            logger.exception("kafka alerts.created failed id=%s", alert.id)
        dispatch(alert)
        try:
            from apps.flywheel.collector import on_alert

            on_alert(camera.id, alert, rtsp=camera.rtsp or "")
        except Exception:
            logger.exception("flywheel alert sample failed id=%s", alert.id)


def _normalize_raw_detections(detections, params):
    """Attach alertType to raw YOLO boxes from the microservice."""
    out = []
    for i, det in enumerate(detections or []):
        if not isinstance(det, dict):
            continue
        item = dict(det)
        bbox = item.get("bbox") or {}
        item["id"] = item.get("id") or (i + 1)
        item["label"] = str(item.get("label") or "")
        try:
            item["confidence"] = float(item.get("confidence") or 0)
        except (TypeError, ValueError):
            item["confidence"] = 0.0
        item["bbox"] = {
            "x": float(bbox.get("x") or 0),
            "y": float(bbox.get("y") or 0),
            "w": float(bbox.get("w") or 0),
            "h": float(bbox.get("h") or 0),
        }
        item["alertType"] = _alert_type_for_label(item.get("label"), params)
        out.append(item)
    return out


def ingest_detections(camera_id, detections, meta=None):
    """
    Post-process detections from yolo-service (or local) and publish frame/alerts.
    Returns the stored frame dict, or None if camera missing/inactive for strategy.
    """
    meta = meta or {}
    close_old_connections()
    try:
        camera = Camera.objects.filter(pk=int(camera_id)).first()
        if not camera or not camera.enabled or not (camera.rtsp or "").strip():
            return None

        params = get_section("detection")
        fps = float(meta.get("fps") or params.get("fps") or 1)
        model_ready = bool(meta.get("modelReady", True))
        infer_active = bool(meta.get("inferActive", True))

        raw_jpeg = meta.get("frameJpeg") or ""
        if raw_jpeg:
            import base64

            try:
                jpeg = base64.b64decode(raw_jpeg)
                if jpeg:
                    rdb.put_last_frame_jpeg(camera.id, jpeg, ttl=30)
            except Exception:
                logger.debug("ingest frameJpeg decode failed camera=%s", camera.id)

        if not should_infer(camera):
            frame = {
                "cameraId": camera.id,
                "timestamp": meta.get("timestamp") or timezone.now().isoformat(),
                "fps": fps,
                "detections": [],
                "inferActive": False,
                "modelReady": model_ready,
            }
            set_frame(camera.id, frame)
            return frame

        dets = _normalize_raw_detections(detections, params)
        dets = filter_by_strategy(camera, dets, params)
        dets = apply_tracking(camera.id, dets, params)
        frame = {
            "cameraId": camera.id,
            "timestamp": meta.get("timestamp") or timezone.now().isoformat(),
            "fps": fps,
            "detections": dets,
            "inferActive": infer_active,
            "modelReady": model_ready,
        }
        set_frame(camera.id, frame)
        try:
            record_frame(camera.id, dets)
        except Exception:
            logger.exception("record_frame failed")
        try:
            broadcast("detection:frame", frame)
        except Exception:
            pass
        if dets:
            try:
                _maybe_alert(camera, dets, params)
            except Exception:
                logger.exception("alert creation failed camera=%s", camera.id)
            try:
                from apps.flywheel.collector import on_frame

                on_frame(camera.id, dets, rtsp=camera.rtsp or "")
            except Exception:
                logger.exception("flywheel sample failed camera=%s", camera.id)
        try:
            flush_metrics()
        except Exception:
            logger.exception("flush_metrics failed")
        return frame
    finally:
        close_old_connections()


def _on_cooldown(camera_id: int) -> bool:
    return rdb.on_cooldown(int(camera_id))


def _put_cooldown(camera_id: int, sec: float | None = None) -> None:
    rdb.put_cooldown(int(camera_id), sec if sec is not None else _COOLDOWN_SEC)


def _reap_unreachable(health: dict | None, params, model_ready: bool) -> None:
    """Stop error workers whose RTSP cannot open; cooldown so they don't thrash."""
    if not health:
        return
    for item in health.get("items") or []:
        cid = int(item.get("cameraId") or 0)
        if not cid or cid not in _remote_started:
            continue
        status = str(item.get("status") or "")
        err = str(item.get("error") or "").lower()
        if status != "error":
            continue
        if not any(h in err for h in _UNREACHABLE_HINTS):
            continue
        logger.warning("remote camera=%s unreachable, cooldown: %s", cid, item.get("error"))
        try:
            remote.stop_camera(cid)
        except Exception:
            pass
        _remote_started.discard(cid)
        _put_cooldown(cid)
        set_frame(cid, {
            "cameraId": cid,
            "timestamp": timezone.now().isoformat(),
            "fps": float(params.get("fps") or 1),
            "detections": [],
            "inferActive": False,
            "modelReady": model_ready,
            "error": item.get("error") or "rtsp unreachable",
        })


def _sync_remote_cameras(active_cameras, params, model_ready: bool):
    """Start/stop remote workers to match strategy-active cameras."""
    global _remote_started, _remote_model_path
    model_path = (params.get("modelPath") or "").strip() or None
    if model_path and model_path != _remote_model_path:
        if _remote_started:
            try:
                remote.stop_all()
            except Exception:
                pass
            _remote_started.clear()
        try:
            remote.reload_model(model_path)
            logger.info("remote YOLO model reloaded: %s", model_path)
        except Exception as exc:
            logger.warning("remote model reload failed: %s", exc)
        _remote_model_path = model_path

    desired = {int(c.id) for c in active_cameras}
    # Stop removed
    for cid in list(_remote_started - desired):
        try:
            remote.stop_camera(cid)
        except Exception as exc:
            logger.warning("remote stop camera=%s failed: %s", cid, exc)
        _remote_started.discard(cid)
        rdb.clear_cooldown(cid)
        set_frame(cid, {
            "cameraId": cid,
            "timestamp": timezone.now().isoformat(),
            "fps": float(params.get("fps") or 1),
            "detections": [],
            "inferActive": False,
            "modelReady": model_ready,
        })

    conf = float(params.get("confidenceThreshold") or 0.5)
    iou = float(params.get("iouThreshold") or 0.45)
    max_det = int(params.get("maxDetections") or 100)
    fps = max(0.5, min(float(params.get("fps") or 1), 2.0))

    for camera in active_cameras:
        cid = int(camera.id)
        if cid in _remote_started:
            continue
        if _on_cooldown(cid):
            set_frame(cid, {
                "cameraId": cid,
                "timestamp": timezone.now().isoformat(),
                "fps": fps,
                "detections": [],
                "inferActive": False,
                "modelReady": model_ready,
                "error": "rtsp cooldown",
            })
            continue
        rtsp = (camera.rtsp or "").strip()
        if not rtsp:
            continue
        try:
            remote.start_camera(
                camera_id=cid,
                rtsp=rtsp,
                conf=conf,
                iou=iou,
                max_det=max_det,
                fps=fps,
                model_path=model_path,
            )
            _remote_started.add(cid)
            logger.info("remote YOLO started camera=%s", cid)
        except Exception as exc:
            logger.warning("remote start camera=%s failed: %s", cid, exc)
            _put_cooldown(cid, 30.0)
            set_frame(cid, {
                "cameraId": cid,
                "timestamp": timezone.now().isoformat(),
                "fps": fps,
                "detections": [],
                "inferActive": False,
                "modelReady": False,
            })


def _loop_remote():
    global _model_ready_cache
    logger.info("推理编排器已启动（remote YOLO 微服务 + 布防策略门控）")
    while not _stop.wait(2.0):
        close_old_connections()
        try:
            params = get_section("detection")
            if not _yolo_enabled(params):
                if _remote_started:
                    try:
                        remote.stop_all()
                    except Exception:
                        pass
                    _remote_started.clear()
                continue

            health = remote.health()
            _model_ready_cache = bool(health and health.get("ready"))
            _reap_unreachable(health, params, _model_ready_cache)

            cameras = list(
                Camera.objects.filter(enabled=True, status="online").only(
                    "id", "name", "rtsp", "status", "enabled", "detection_types"
                )
            )
            active = []
            for camera in cameras:
                if should_infer(camera):
                    active.append(camera)
                else:
                    if camera.id in _remote_started:
                        try:
                            remote.stop_camera(camera.id)
                        except Exception:
                            pass
                        _remote_started.discard(camera.id)
                    set_frame(camera.id, {
                        "cameraId": camera.id,
                        "timestamp": timezone.now().isoformat(),
                        "fps": float(params.get("fps") or 1),
                        "detections": [],
                        "inferActive": False,
                        "modelReady": _model_ready_cache,
                    })

            if health is None:
                logger.warning("YOLO service unavailable at %s", remote.service_url())
                for camera in active:
                    set_frame(camera.id, {
                        "cameraId": camera.id,
                        "timestamp": timezone.now().isoformat(),
                        "fps": float(params.get("fps") or 1),
                        "detections": [],
                        "inferActive": False,
                        "modelReady": False,
                    })
                continue

            _sync_remote_cameras(active, params, _model_ready_cache)
        except Exception:
            logger.exception("remote orchestrator iteration failed")
        finally:
            close_old_connections()


def _loop_local():
    global _rr_index
    logger.info("YOLOv8 推理流水线已启动（local 模式 + 布防策略门控）")
    params0 = get_section("detection")
    if _yolo_enabled(params0):
        yolo_engine.ensure_model(params0.get("modelPath"))

    while not _stop.wait(0.2):
        close_old_connections()
        try:
            params = get_section("detection")
            fps = max(0.5, min(float(params.get("fps") or 1), 2.0))
            interval = max(0.8, 1.0 / fps)

            cameras = list(
                Camera.objects.filter(enabled=True, status="online").only(
                    "id", "name", "rtsp", "status", "enabled", "detection_types"
                )
            )
            active = []
            for camera in cameras:
                if should_infer(camera):
                    active.append(camera)
                else:
                    set_frame(camera.id, {
                        "cameraId": camera.id,
                        "timestamp": timezone.now().isoformat(),
                        "fps": fps,
                        "detections": [],
                        "inferActive": False,
                        "modelReady": yolo_engine.is_ready(),
                    })

            if not active:
                _stop.wait(interval)
                continue

            _rr_index = (_rr_index + 1) % len(active)
            camera = active[_rr_index]
            detections = infer_frame(camera, params)
            ingest_detections(
                camera.id,
                detections,
                {
                    "fps": fps,
                    "modelReady": yolo_engine.is_ready(),
                    "inferActive": True,
                    "timestamp": timezone.now().isoformat(),
                },
            )
        except Exception:
            logger.exception("local inference loop iteration failed")
        finally:
            close_old_connections()
        _stop.wait(interval)


def _loop():
    _loop_remote()


def start_pipeline():
    global _thread
    if _thread and _thread.is_alive():
        return
    raw = (os.environ.get("YOLO_INFER_MODE") or "remote").strip().lower()
    if raw == "local" or os.environ.get("YOLO_ALLOW_LOCAL", "").strip():
        logger.warning("YOLO_INFER_MODE=local / YOLO_ALLOW_LOCAL ignored; in-process YOLO races Kafka")
    _stop.clear()
    _thread = threading.Thread(target=_loop_remote, name="yolo-pipeline", daemon=True)
    _thread.start()


def stop_pipeline():
    _stop.set()
    if remote.infer_mode() == "remote":
        try:
            remote.stop_all()
        except Exception:
            pass
        _remote_started.clear()
    frame_source.release_all()

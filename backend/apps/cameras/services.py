from django.utils import timezone
from apps.inference.runtime import get_latest_frame
from .models import Camera, CameraRecording, CameraRuntimeState, CameraSnapshot


_PTZ_DELTA = {
    "up": (0, 5, 0),
    "down": (0, -5, 0),
    "left": (-5, 0, 0),
    "right": (5, 0, 0),
    "zoomin": (0, 0, 0.2),
    "zoomout": (0, 0, -0.2),
}


def get_runtime(camera):
    state, _ = CameraRuntimeState.objects.get_or_create(camera=camera)
    return state


def serialize_ptz(state):
    return {
        "pan": round(state.pan, 2),
        "tilt": round(state.tilt, 2),
        "zoom": round(state.zoom, 2),
        "lastDirection": state.last_direction or None,
        "updatedAt": state.updated_at.isoformat() if state.updated_at else None,
    }


def apply_ptz(camera, direction, speed=1):
    if direction not in _PTZ_DELTA:
        raise ValueError("无效的云台方向")
    speed = float(speed or 1)
    if speed <= 0:
        speed = 1
    dpan, dtilt, dzoom = _PTZ_DELTA[direction]
    state = get_runtime(camera)
    state.pan = max(-180, min(180, state.pan + dpan * speed))
    state.tilt = max(-90, min(90, state.tilt + dtilt * speed))
    state.zoom = max(1, min(10, state.zoom + dzoom * speed))
    state.last_direction = direction
    state.save()
    return state


def is_recording(camera_id):
    return CameraRecording.objects.filter(camera_id=camera_id, status="recording").exists()


def active_recording(camera):
    return CameraRecording.objects.filter(camera=camera, status="recording").first()


def serialize_recording(rec):
    if not rec:
        return None
    return {
        "id": rec.id,
        "cameraId": rec.camera_id,
        "status": rec.status,
        "operator": rec.operator,
        "startedAt": rec.started_at.isoformat() if rec.started_at else None,
        "stoppedAt": rec.stopped_at.isoformat() if rec.stopped_at else None,
    }


def serialize_snapshot(snap):
    return {
        "id": snap.id,
        "cameraId": snap.camera_id,
        "cameraName": snap.camera.name if snap.camera_id else "",
        "operator": snap.operator,
        "detectionCount": snap.detection_count,
        "detections": snap.detections or [],
        "fps": snap.fps,
        "createdAt": snap.created_at.isoformat() if snap.created_at else None,
    }


def normalize_detection(det, idx=0):
    """Unify detection box: always { id, label, confidence, bbox:{x,y,w,h} } with 0~1 coords."""
    if not isinstance(det, dict):
        return {
            "id": idx,
            "label": "unknown",
            "confidence": 0,
            "bbox": {"x": 0, "y": 0, "w": 0, "h": 0},
        }
    bbox = det.get("bbox") if isinstance(det.get("bbox"), dict) else None
    if not bbox:
        bbox = {
            "x": det.get("x", 0),
            "y": det.get("y", 0),
            "w": det.get("w", 0),
            "h": det.get("h", 0),
        }
    return {
        "id": det.get("id", idx),
        "label": det.get("label") or "unknown",
        "confidence": float(det.get("confidence") or 0),
        "bbox": {
            "x": float(bbox.get("x") or 0),
            "y": float(bbox.get("y") or 0),
            "w": float(bbox.get("w") or 0),
            "h": float(bbox.get("h") or 0),
        },
    }


def normalize_frame(camera_id, frame=None):
    frame = frame or {}
    detections = [normalize_detection(d, i) for i, d in enumerate(frame.get("detections") or [])]
    return {
        "cameraId": int(camera_id),
        "timestamp": frame.get("timestamp"),
        "fps": float(frame.get("fps") or 0),
        "detectionCount": len(detections),
        "detections": detections,
        "inferActive": bool(frame.get("inferActive")),
        "modelReady": bool(frame.get("modelReady")),
    }


def build_monitor_camera(camera, frames=None, recording_ids=None, runtime=None, streams=None):
    frames = frames if frames is not None else {}
    raw_frame = frames.get(camera.id) or {}
    frame = normalize_frame(camera.id, raw_frame)
    runtime = runtime or get_runtime(camera)
    from apps.cameras.health import camera_health

    health = camera_health(camera, streams=streams)
    live = bool(health.get("live"))
    ready = bool(health.get("hlsReady"))
    return {
        "id": camera.id,
        "name": camera.name,
        "location": camera.location or "",
        "ip": camera.ip or "",
        "rtsp": camera.rtsp or "",
        "type": camera.type or "other",
        "username": camera.username or "",
        "resolution": camera.resolution or "",
        "channels": camera.channels or 1,
        "status": camera.status,  # online | offline
        "enabled": bool(camera.enabled),
        "previewEligible": health.get("previewEligible"),
        "live": live,
        "rtspConfigured": health.get("rtspConfigured"),
        "hlsReady": ready,
        "previewReady": ready,
        "hasLastFrame": health.get("hasLastFrame"),
        "inferActive": health.get("inferActive") or frame["inferActive"],
        "armed": health.get("armed"),
        "detectionTypes": camera.detection_types or [],
        "createdAt": camera.created_at.isoformat() if camera.created_at else None,
        "updatedAt": camera.updated_at.isoformat() if camera.updated_at else None,
        "detectionCount": frame["detectionCount"] if live else 0,
        "fps": frame["fps"] if live else 0,
        "lastFrameAt": frame["timestamp"] or health.get("lastFrameAt"),
        "recording": camera.id in recording_ids if recording_ids is not None else is_recording(camera.id),
        "ptz": serialize_ptz(runtime),
        "hlsUrl": health.get("hlsUrl"),
        "streamStatus": health.get("streamStatus") or "idle",
        "streamMode": health.get("streamMode"),
        "playlistReady": ready,
        "mtxPath": health.get("mtxPath"),
    }


def build_monitor_wall():
    """
    Canonical monitor payload:
      summary, cameras[], frames{cameraId: DetectionFrame},
      recentAlerts[], unhandledCount, serverTime
    """
    from apps.alerts.models import Alert
    from apps.alerts.serializers import AlertSerializer
    from apps.common import rdb

    cameras = list(Camera.objects.all().order_by("id"))
    cameras = sorted(cameras, key=lambda c: (0 if c.enabled else 1, 0 if c.status == "online" else 1, c.id))
    ids = [cam.id for cam in cameras]
    streams = rdb.get_all_stream_health()
    frames = rdb.get_last_frame_metas(ids)
    runtimes = {item.camera_id: item for item in CameraRuntimeState.objects.filter(camera_id__in=ids)}
    missing = [cam for cam in cameras if cam.id not in runtimes]
    if missing:
        CameraRuntimeState.objects.bulk_create([CameraRuntimeState(camera=cam) for cam in missing])
        runtimes = {item.camera_id: item for item in CameraRuntimeState.objects.filter(camera_id__in=ids)}
    recording_ids = set(
        CameraRecording.objects.filter(status="recording").values_list("camera_id", flat=True)
    )
    items = [build_monitor_camera(cam, frames, recording_ids, runtimes.get(cam.id), streams) for cam in cameras]

    frame_map = {str(cam.id): normalize_frame(cam.id, frames.get(cam.id)) for cam in cameras}

    online = sum(1 for c in items if c["live"])
    # Avoid scanning tens of thousands of unhandled rows on every poll
    recent_qs = (
        Alert.objects.filter(status="unhandled")
        .select_related("camera")
        .order_by("-triggered_at")[:20]
    )
    recent_alerts = AlertSerializer(list(recent_qs), many=True).data
    unhandled_count = Alert.objects.filter(status="unhandled").count()

    return {
        "summary": {
            "cameraTotal": len(items),
            "cameraOnline": online,
            "cameraOffline": len(items) - online,
            "unhandledAlertCount": unhandled_count,
        },
        "cameras": items,
        "frames": frame_map,
        "recentAlerts": recent_alerts,
        "unhandledCount": unhandled_count,
        # Compat aliases
        "alerts": {"list": recent_alerts, "total": unhandled_count},
        "serverTime": timezone.localtime().isoformat(),
    }


def create_snapshot(camera, operator=""):
    frame = get_latest_frame(camera.id) or {}
    detections = frame.get("detections") or []
    return CameraSnapshot.objects.create(
        camera=camera,
        operator=operator or "",
        detections=detections,
        detection_count=len(detections),
        fps=frame.get("fps"),
    )


def start_recording(camera, operator=""):
    existing = active_recording(camera)
    if existing:
        return existing, False
    rec = CameraRecording.objects.create(camera=camera, operator=operator or "", status="recording")
    return rec, True


def stop_recording(camera):
    rec = active_recording(camera)
    if not rec:
        return None
    rec.status = "stopped"
    rec.stopped_at = timezone.now()
    rec.save(update_fields=["status", "stopped_at"])
    return rec

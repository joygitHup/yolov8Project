from django.utils import timezone
from apps.inference.runtime import get_all_frames, get_latest_frame
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


def build_monitor_camera(camera, frames=None, recording_ids=None, runtime=None):
    frames = frames if frames is not None else get_all_frames()
    frame = frames.get(camera.id) or get_latest_frame(camera.id) or {}
    detections = frame.get("detections") or []
    live = bool(camera.enabled and camera.status == "online")
    runtime = runtime or get_runtime(camera)
    return {
        "id": camera.id,
        "name": camera.name,
        "location": camera.location,
        "ip": camera.ip,
        "rtsp": camera.rtsp,
        "type": camera.type,
        "username": camera.username,
        "resolution": camera.resolution,
        "channels": camera.channels,
        "status": camera.status,
        "enabled": camera.enabled,
        "detectionTypes": camera.detection_types or [],
        "createdAt": camera.created_at.isoformat() if camera.created_at else None,
        "updatedAt": camera.updated_at.isoformat() if camera.updated_at else None,
        "live": live,
        "detectionCount": len(detections) if live else 0,
        "fps": frame.get("fps") if live else 0,
        "lastFrameAt": frame.get("timestamp") if live else None,
        "recording": camera.id in recording_ids if recording_ids is not None else is_recording(camera.id),
        "ptz": serialize_ptz(runtime),
    }


def build_monitor_wall():
    cameras = list(Camera.objects.all())
    frames = get_all_frames()
    ids = [cam.id for cam in cameras]
    runtimes = {item.camera_id: item for item in CameraRuntimeState.objects.filter(camera_id__in=ids)}
    missing = [cam for cam in cameras if cam.id not in runtimes]
    if missing:
        CameraRuntimeState.objects.bulk_create([CameraRuntimeState(camera=cam) for cam in missing])
        runtimes = {item.camera_id: item for item in CameraRuntimeState.objects.filter(camera_id__in=ids)}
    recording_ids = set(
        CameraRecording.objects.filter(status="recording").values_list("camera_id", flat=True)
    )
    items = [build_monitor_camera(cam, frames, recording_ids, runtimes.get(cam.id)) for cam in cameras]
    frame_map = {}
    for cam in cameras:
        if not cam.enabled or cam.status != "online":
            frame_map[str(cam.id)] = {
                "cameraId": cam.id,
                "timestamp": None,
                "fps": 0,
                "detections": [],
            }
            continue
        frame_map[str(cam.id)] = frames.get(cam.id) or get_latest_frame(cam.id) or {
            "cameraId": cam.id,
            "timestamp": None,
            "fps": 0,
            "detections": [],
        }
    return items, frame_map


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

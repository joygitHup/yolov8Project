from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app import engine, face as face_mod
from app.auth import require_service_token
from app.schemas import ReloadModelRequest, StartCameraRequest, StopCameraRequest
from app.worker import manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("yolo.service")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    path = os.environ.get("YOLO_WEIGHTS")
    ok = engine.ensure_model(path)
    logger.info("startup model_ready=%s path=%s err=%s", ok, engine.current_model_path(), engine.get_load_error())
    face_mod.prewarm()
    yield
    manager.stop_all()
    logger.info("shutdown complete")


app = FastAPI(title="YOLOv8 Inference Service", version="1.0.0", lifespan=lifespan)


@app.get("/health")
def health(_token: str = Depends(require_service_token)):
    cams = manager.list_cameras()
    return {
        "ready": engine.is_ready(),
        "modelPath": engine.current_model_path(),
        "device": engine.resolve_device(),
        "cameras": len(cams),
        "loadError": engine.get_load_error(),
        "face": face_mod.face_status(),
        "items": [c.model_dump() for c in cams],
    }


@app.get("/cameras")
def list_cameras(_token: str = Depends(require_service_token)):
    return {"list": [c.model_dump() for c in manager.list_cameras()]}


@app.post("/cameras/start")
def start_camera(body: StartCameraRequest, _token: str = Depends(require_service_token)):
    if not (body.rtsp or "").strip():
        raise HTTPException(status_code=400, detail="rtsp is required")
    if not engine.is_ready():
        engine.ensure_model(body.modelPath)
    status = manager.start_camera(body)
    return status.model_dump()


@app.post("/cameras/stop")
def stop_camera(body: StopCameraRequest, _token: str = Depends(require_service_token)):
    status = manager.stop_camera(body.cameraId)
    if not status:
        return {"cameraId": body.cameraId, "status": "idle", "message": "not running"}
    return status.model_dump()


@app.post("/cameras/stop-all")
def stop_all(_token: str = Depends(require_service_token)):
    n = manager.stop_all()
    return {"stopped": n}


@app.post("/model/reload")
def reload_model(body: ReloadModelRequest, _token: str = Depends(require_service_token)):
    path = (body.modelPath or "").strip() or None
    ok = engine.ensure_model(path, force=True)
    if not ok:
        raise HTTPException(status_code=400, detail=engine.get_load_error() or "load failed")
    return {
        "ready": True,
        "modelPath": engine.current_model_path(),
        "device": engine.resolve_device(),
    }


@app.get("/faces")
def faces_list(_token: str = Depends(require_service_token)):
    return {"list": face_mod.list_faces()}


@app.post("/faces/enroll")
async def faces_enroll(
    name: str = Form(...),
    image: UploadFile = File(...),
    _token: str = Depends(require_service_token),
):
    data = await image.read()
    try:
        return face_mod.enroll_face(name, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.delete("/faces/{face_id}")
def faces_delete(face_id: str, _token: str = Depends(require_service_token)):
    if not face_mod.delete_face(face_id):
        raise HTTPException(status_code=404, detail="faceId not found")
    return {"deleted": face_id}


@app.get("/faces/{face_id}/photo")
def face_photo(face_id: str, _token: str = Depends(require_service_token)):
    path = face_mod.face_photo_path(face_id)
    if not path:
        raise HTTPException(status_code=404, detail="no photo")
    with open(path, "rb") as fh:
        return Response(content=fh.read(), media_type="image/jpeg")

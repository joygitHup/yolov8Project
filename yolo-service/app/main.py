from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from app import engine
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
    yield
    manager.stop_all()
    logger.info("shutdown complete")


app = FastAPI(title="YOLOv8 Inference Service", version="1.0.0", lifespan=lifespan)


@app.get("/health")
def health():
    cams = manager.list_cameras()
    return {
        "ready": engine.is_ready(),
        "modelPath": engine.current_model_path(),
        "device": engine.resolve_device(),
        "cameras": len(cams),
        "loadError": engine.get_load_error(),
        "items": [c.model_dump() for c in cams],
    }


@app.get("/cameras")
def list_cameras():
    return {"list": [c.model_dump() for c in manager.list_cameras()]}


@app.post("/cameras/start")
def start_camera(body: StartCameraRequest):
    if not (body.rtsp or "").strip():
        raise HTTPException(status_code=400, detail="rtsp is required")
    if not engine.is_ready():
        engine.ensure_model(body.modelPath)
    status = manager.start_camera(body)
    return status.model_dump()


@app.post("/cameras/stop")
def stop_camera(body: StopCameraRequest):
    status = manager.stop_camera(body.cameraId)
    if not status:
        return {"cameraId": body.cameraId, "status": "idle", "message": "not running"}
    return status.model_dump()


@app.post("/cameras/stop-all")
def stop_all():
    n = manager.stop_all()
    return {"stopped": n}


@app.post("/model/reload")
def reload_model(body: ReloadModelRequest):
    path = (body.modelPath or "").strip() or None
    ok = engine.ensure_model(path, force=True)
    if not ok:
        raise HTTPException(status_code=400, detail=engine.get_load_error() or "load failed")
    return {
        "ready": True,
        "modelPath": engine.current_model_path(),
        "device": engine.resolve_device(),
    }

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class StartCameraRequest(BaseModel):
    cameraId: int
    rtsp: str
    conf: float = 0.5
    iou: float = 0.45
    maxDet: int = 100
    fps: float = 1.0
    modelPath: Optional[str] = None
    callbackUrl: str = "http://127.0.0.1:3001/api/inference/ingest"
    ingestToken: Optional[str] = None


class StopCameraRequest(BaseModel):
    cameraId: int


class BBox(BaseModel):
    x: float
    y: float
    w: float
    h: float


class Detection(BaseModel):
    id: int
    label: str
    confidence: float
    bbox: BBox


class DetectionFrame(BaseModel):
    cameraId: int
    timestamp: str
    fps: float
    detections: list[dict[str, Any]] = Field(default_factory=list)
    modelReady: bool = True
    inferActive: bool = True


class CameraStatus(BaseModel):
    cameraId: int
    rtsp: str
    status: str  # running | stopping | error | idle
    fps: float
    conf: float
    error: str = ""
    lastCallbackOk: bool = False
    shared: bool = False
    sharedWith: list[int] = Field(default_factory=list)


class ReloadModelRequest(BaseModel):
    modelPath: Optional[str] = None

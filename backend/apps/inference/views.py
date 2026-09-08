"""Ingest detection frames from the YOLO microservice."""
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from apps.common.apiview import APIView
from rest_framework.exceptions import AuthenticationFailed, ValidationError

from apps.inference.pipeline import ingest_detections
from apps.inference.remote import ingest_token


class InferenceIngestView(APIView):
    """Receive detection callbacks from yolo-service (no user JWT)."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        expected = ingest_token()
        got = (request.headers.get("X-Ingest-Token") or "").strip()
        if not expected or got != expected:
            raise AuthenticationFailed("invalid ingest token")

        camera_id = request.data.get("cameraId")
        if camera_id is None:
            raise ValidationError("cameraId is required")
        detections = request.data.get("detections")
        if detections is None:
            detections = []
        if not isinstance(detections, list):
            raise ValidationError("detections must be an array")

        meta = {
            "timestamp": request.data.get("timestamp"),
            "fps": request.data.get("fps"),
            "modelReady": request.data.get("modelReady", True),
            "inferActive": request.data.get("inferActive", True),
            "frameJpeg": request.data.get("frameJpeg"),
        }
        frame = ingest_detections(int(camera_id), detections, meta)
        if frame is None:
            return Response({"ok": False, "message": "camera not found or inactive"}, status=404)
        return Response({"ok": True, "cameraId": frame.get("cameraId"), "detectionCount": len(frame.get("detections") or [])})

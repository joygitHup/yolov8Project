from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Q
from apps.alerts.models import Alert
from apps.alerts.serializers import AlertSerializer
from apps.common.pagination import paginate_qs
from apps.common.permissions import IsAdminOrOperator
from apps.inference.runtime import get_latest_frame
from .models import Camera, CameraRecording, CameraSnapshot
from .serializers import CameraSerializer
from . import services


def _camera_or_404(pk):
    camera = Camera.objects.filter(pk=pk).first()
    if not camera:
        raise NotFound("摄像头不存在")
    return camera


class CameraListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), IsAdminOrOperator()]
        return [IsAuthenticated()]

    def get(self, request):
        qs = Camera.objects.all()
        keyword = request.query_params.get("keyword") or ""
        status = request.query_params.get("status") or ""
        cam_type = request.query_params.get("type") or ""
        if keyword:
            qs = qs.filter(
                Q(name__icontains=keyword) | Q(location__icontains=keyword) | Q(ip__icontains=keyword)
            )
        if status:
            qs = qs.filter(status=status)
        if cam_type:
            qs = qs.filter(type=cam_type)
        return Response(paginate_qs(qs, request, CameraSerializer))

    def post(self, request):
        if not request.data.get("name") or not request.data.get("rtsp"):
            raise ValidationError("名称和RTSP地址不能为空")
        ser = CameraSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        camera = ser.save(
            detection_types=request.data.get("detectionTypes") or ["intrusion", "parking", "fire"],
            status="online",
        )
        return Response(CameraSerializer(camera).data)


class CameraAllView(APIView):
    def get(self, request):
        # Same records as camera management, unpaginated.
        return Response(CameraSerializer(Camera.objects.all(), many=True).data)


class CameraMonitorWallView(APIView):
    def get(self, request):
        cameras, frames = services.build_monitor_wall()
        alerts = Alert.objects.filter(status="unhandled")[:20]
        return Response({
            "cameras": cameras,
            "frames": frames,
            "alerts": {
                "list": AlertSerializer(alerts, many=True).data,
                "total": Alert.objects.filter(status="unhandled").count(),
            },
        })


class CameraDetailView(APIView):
    def get_permissions(self):
        if self.request.method in ("PUT", "DELETE"):
            return [IsAuthenticated(), IsAdminOrOperator()]
        return [IsAuthenticated()]

    def get(self, request, pk):
        return Response(CameraSerializer(_camera_or_404(pk)).data)

    def put(self, request, pk):
        camera = _camera_or_404(pk)
        ser = CameraSerializer(camera, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        if "detectionTypes" in request.data:
            camera.detection_types = request.data.get("detectionTypes")
        ser.save()
        camera.refresh_from_db()
        return Response(CameraSerializer(camera).data)

    def delete(self, request, pk):
        _camera_or_404(pk).delete()
        return Response({"message": "删除成功"})


class CameraBatchDeleteView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrOperator]

    def post(self, request):
        ids = request.data.get("ids")
        if not isinstance(ids, list):
            raise ValidationError("参数错误")
        count, _ = Camera.objects.filter(id__in=ids).delete()
        return Response({"message": f"成功删除 {count} 个摄像头", "count": count})


class CameraToggleView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrOperator]

    def post(self, request, pk):
        camera = _camera_or_404(pk)
        camera.enabled = not camera.enabled
        camera.save(update_fields=["enabled"])
        return Response({"enabled": camera.enabled})


class CameraPtzView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), IsAdminOrOperator()]
        return [IsAuthenticated()]

    def get(self, request, pk):
        camera = _camera_or_404(pk)
        return Response(services.serialize_ptz(services.get_runtime(camera)))

    def post(self, request, pk):
        camera = _camera_or_404(pk)
        direction = request.data.get("direction")
        try:
            state = services.apply_ptz(camera, direction, request.data.get("speed") or 1)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        return Response({
            "success": True,
            "message": f"云台{direction}控制指令已发送",
            "direction": direction,
            "speed": request.data.get("speed") or 1,
            "ptz": services.serialize_ptz(state),
        })


class CameraDetectionView(APIView):
    def get(self, request, pk):
        camera = _camera_or_404(pk)
        live = bool(camera.enabled and camera.status == "online")
        frame = get_latest_frame(camera.id) if live else None
        return Response(frame or {
            "cameraId": camera.id,
            "timestamp": None,
            "fps": 0,
            "detections": [],
        })


class CameraSnapshotView(APIView):
    def get(self, request, pk):
        camera = _camera_or_404(pk)
        qs = CameraSnapshot.objects.filter(camera=camera)[:20]
        return Response([services.serialize_snapshot(item) for item in qs])

    def post(self, request, pk):
        camera = _camera_or_404(pk)
        snap = services.create_snapshot(camera, getattr(request.user, "username", ""))
        return Response(services.serialize_snapshot(snap))


class CameraRecordView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrOperator]

    def get(self, request, pk):
        camera = _camera_or_404(pk)
        rec = services.active_recording(camera)
        history = CameraRecording.objects.filter(camera=camera)[:10]
        return Response({
            "recording": bool(rec),
            "current": services.serialize_recording(rec),
            "history": [services.serialize_recording(item) for item in history],
        })

    def post(self, request, pk):
        camera = _camera_or_404(pk)
        action = (request.data.get("action") or "toggle").lower()
        operator = getattr(request.user, "username", "")
        if action == "start":
            rec, created = services.start_recording(camera, operator)
            return Response({
                "recording": True,
                "started": created,
                "current": services.serialize_recording(rec),
            })
        if action == "stop":
            rec = services.stop_recording(camera)
            if not rec:
                raise ValidationError("当前没有正在进行的录制")
            return Response({
                "recording": False,
                "current": services.serialize_recording(rec),
            })
        rec = services.active_recording(camera)
        if rec:
            rec = services.stop_recording(camera)
            return Response({
                "recording": False,
                "current": services.serialize_recording(rec),
            })
        rec, _ = services.start_recording(camera, operator)
        return Response({
            "recording": True,
            "started": True,
            "current": services.serialize_recording(rec),
        })

from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Q
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
        qs = Camera.objects.all().order_by("-id")
        keyword = (request.query_params.get("keyword") or "").strip()
        status = (request.query_params.get("status") or "").strip()
        cam_type = (request.query_params.get("type") or "").strip()
        enabled = request.query_params.get("enabled")
        if keyword:
            qs = qs.filter(
                Q(name__icontains=keyword) | Q(location__icontains=keyword) | Q(ip__icontains=keyword)
            )
        if status in ("online", "offline"):
            qs = qs.filter(status=status)
        if cam_type in ("hikvision", "dahua", "other"):
            qs = qs.filter(type=cam_type)
        if enabled is not None and str(enabled).strip() != "":
            val = str(enabled).strip().lower()
            if val in ("1", "true", "yes"):
                qs = qs.filter(enabled=True)
            elif val in ("0", "false", "no"):
                qs = qs.filter(enabled=False)
        return Response(paginate_qs(qs, request, CameraSerializer))

    def post(self, request):
        data = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)
        if not data.get("name") or not data.get("rtsp"):
            raise ValidationError("名称和RTSP地址不能为空")
        if "detectionTypes" not in data:
            data["detectionTypes"] = ["intrusion", "parking", "fire"]
        if "status" not in data:
            data["status"] = "offline"
        if "enabled" not in data:
            data["enabled"] = True
        ser = CameraSerializer(data=data)
        ser.is_valid(raise_exception=True)
        camera = ser.save()
        return Response(CameraSerializer(camera).data)


class CameraAllView(APIView):
    def get(self, request):
        qs = Camera.objects.all().order_by("id")
        status = (request.query_params.get("status") or "").strip()
        enabled = request.query_params.get("enabled")
        if status in ("online", "offline"):
            qs = qs.filter(status=status)
        if enabled is not None and str(enabled).strip() != "":
            val = str(enabled).strip().lower()
            if val in ("1", "true", "yes"):
                qs = qs.filter(enabled=True)
            elif val in ("0", "false", "no"):
                qs = qs.filter(enabled=False)
        return Response(CameraSerializer(qs, many=True).data)


class CameraMonitorWallView(APIView):
    def get(self, request):
        return Response(services.build_monitor_wall())


class CameraDetailView(APIView):
    def get_permissions(self):
        if self.request.method in ("PUT", "DELETE"):
            return [IsAuthenticated(), IsAdminOrOperator()]
        return [IsAuthenticated()]

    def get(self, request, pk):
        return Response(CameraSerializer(_camera_or_404(pk)).data)

    def put(self, request, pk):
        camera = _camera_or_404(pk)
        data = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)
        ser = CameraSerializer(camera, data=data, partial=True)
        ser.is_valid(raise_exception=True)
        camera = ser.save()
        return Response(CameraSerializer(camera).data)

    def delete(self, request, pk):
        camera = _camera_or_404(pk)
        name = camera.name
        camera.delete()
        return Response({"message": "删除成功", "id": pk, "name": name})


class CameraBatchDeleteView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrOperator]

    def post(self, request):
        ids = request.data.get("ids")
        if not isinstance(ids, list) or not ids:
            raise ValidationError("ids 必须为非空数组")
        cleaned = []
        for item in ids:
            try:
                cleaned.append(int(item))
            except (TypeError, ValueError):
                continue
        if not cleaned:
            raise ValidationError("ids 无效")
        count, _ = Camera.objects.filter(id__in=cleaned).delete()
        return Response({"message": f"成功删除 {count} 个摄像头", "count": count, "ids": cleaned})


class CameraToggleView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrOperator]

    def post(self, request, pk):
        camera = _camera_or_404(pk)
        if "enabled" in request.data:
            camera.enabled = bool(request.data.get("enabled"))
        else:
            camera.enabled = not camera.enabled
        camera.save(update_fields=["enabled", "updated_at"])
        return Response(CameraSerializer(camera).data)


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
        frame = get_latest_frame(camera.id)
        return Response(services.normalize_frame(camera.id, frame))


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

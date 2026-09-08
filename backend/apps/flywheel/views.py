from django.db.models import Count
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common import storage
from apps.common.permissions import IsAdminOrOperator
from apps.flywheel.dataset import (
    DATA_YAML_KEY,
    DATASET_PREFIX,
    IMAGES_PREFIX,
    LABELS_PREFIX,
    REVIEWED_IMAGES_PREFIX,
    REVIEWED_LABELS_PREFIX,
)
from apps.flywheel.models import FlywheelSample
from apps.flywheel.services import (
    approve_sample,
    camera_name_map,
    discard_sample,
    next_pending,
    sample_to_dict,
    save_boxes,
)
from apps.realtime.broadcast import broadcast
from apps.systemcfg.services import get_section, normalize_flywheel, save_section
from django.conf import settings as dj_settings


def _get_sample(pk) -> FlywheelSample:
    sample = FlywheelSample.objects.filter(pk=pk).first()
    if not sample:
        raise NotFound("样本不存在")
    return sample


class FlywheelConfigView(APIView):
    def get_permissions(self):
        if self.request.method == "PUT":
            return [IsAuthenticated(), IsAdminOrOperator()]
        return [IsAuthenticated()]

    def get(self, request):
        return Response(get_section("flywheel"))

    def put(self, request):
        from apps.flywheel.jobs import job_write_yaml
        from apps.systemcfg.services import deep_merge

        before = get_section("flywheel")
        flywheel = normalize_flywheel(deep_merge(before, dict(request.data)))
        save_section("flywheel", flywheel)
        try:
            job_write_yaml({})
        except Exception:
            pass
        broadcast("config:updated", {"section": "flywheel", "flywheel": flywheel})
        return Response({"message": "数据采集配置已更新", "flywheel": flywheel})


class FlywheelStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
        qs = FlywheelSample.objects.all()
        by_source = {row["source"]: row["n"] for row in qs.values("source").annotate(n=Count("id"))}
        by_status = {row["status"]: row["n"] for row in qs.values("status").annotate(n=Count("id"))}
        return Response({
            "flywheel": get_section("flywheel"),
            "bucket": getattr(dj_settings, "MINIO_BUCKET", "yolov8pro"),
            "prefix": DATASET_PREFIX,
            "imagesPrefix": IMAGES_PREFIX,
            "labelsPrefix": LABELS_PREFIX,
            "reviewedImagesPrefix": REVIEWED_IMAGES_PREFIX,
            "reviewedLabelsPrefix": REVIEWED_LABELS_PREFIX,
            "dataYamlKey": DATA_YAML_KEY,
            "total": qs.count(),
            "today": qs.filter(created_at__gte=today).count(),
            "bySource": {
                "alert": int(by_source.get("alert") or 0),
                "uncertain": int(by_source.get("uncertain") or 0),
            },
            "byStatus": {
                "pending": int(by_status.get("pending") or 0),
                "approved": int(by_status.get("approved") or 0),
                "discarded": int(by_status.get("discarded") or 0),
            },
        })


class FlywheelSampleListView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrOperator]

    def get(self, request):
        qs = FlywheelSample.objects.all().order_by("id")
        status = (request.query_params.get("status") or "").strip()
        if status:
            if status not in ("pending", "approved", "discarded"):
                raise ValidationError("status 无效，可选：pending / approved / discarded")
            qs = qs.filter(status=status)
        source = (request.query_params.get("source") or "").strip()
        if source:
            if source not in ("alert", "uncertain"):
                raise ValidationError("source 无效，可选：alert / uncertain")
            qs = qs.filter(source=source)
        try:
            page = max(int(request.query_params.get("page", 1)), 1)
        except (TypeError, ValueError):
            page = 1
        try:
            page_size = min(max(int(request.query_params.get("pageSize", 20)), 1), 100)
        except (TypeError, ValueError):
            page_size = 20
        total = qs.count()
        start = (page - 1) * page_size
        items = list(qs[start:start + page_size])
        names = camera_name_map({row.camera_id for row in items})
        return Response({
            "list": [sample_to_dict(row, camera_names=names) for row in items],
            "total": total,
            "page": page,
            "pageSize": page_size,
        })


class FlywheelSampleNextView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrOperator]

    def get(self, request):
        try:
            after_id = int(request.query_params.get("afterId") or 0)
        except (TypeError, ValueError):
            after_id = 0
        sample = next_pending(after_id=after_id)
        if not sample:
            return Response({"sample": None})
        return Response({"sample": sample_to_dict(sample, with_boxes=True)})


class FlywheelSampleDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrOperator]

    def get(self, request, pk):
        return Response(sample_to_dict(_get_sample(pk), with_boxes=True))

    def put(self, request, pk):
        sample = _get_sample(pk)
        if "boxes" not in request.data:
            raise ValidationError("boxes 必填")
        try:
            sample = save_boxes(sample, request.data.get("boxes"))
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(sample_to_dict(sample, with_boxes=True))


class FlywheelSampleImageView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrOperator]

    def get(self, request, pk):
        sample = _get_sample(pk)
        data = storage.get_bytes(sample.image_key)
        if not data:
            raise NotFound("样本图片不存在")
        resp = HttpResponse(data, content_type="image/jpeg")
        resp["Cache-Control"] = "private, max-age=60"
        return resp


class FlywheelSampleApproveView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrOperator]

    def post(self, request, pk):
        sample = _get_sample(pk)
        boxes = request.data.get("boxes") if isinstance(request.data, dict) else None
        try:
            sample = approve_sample(
                sample,
                raw_boxes=boxes,
                operator=getattr(request.user, "username", "") or "user",
            )
        except RuntimeError as exc:
            raise ValidationError(str(exc)) from exc
        return Response({"message": "已通过并写入训练集", "sample": sample_to_dict(sample, with_boxes=True)})


class FlywheelSampleDiscardView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrOperator]

    def post(self, request, pk):
        sample = discard_sample(
            _get_sample(pk),
            operator=getattr(request.user, "username", "") or "user",
        )
        return Response({"message": "已丢弃", "sample": sample_to_dict(sample, with_boxes=True)})


class FlywheelTrainView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrOperator]

    def get(self, request):
        from apps.flywheel.trainer import latest_run, run_to_dict

        run = latest_run()
        cfg = get_section("flywheel")
        approved = FlywheelSample.objects.filter(status="approved").count()
        return Response({
            "run": run_to_dict(run) if run else None,
            "approved": approved,
            "minReviewed": int(cfg.get("minReviewed") or 5),
            "trainRoot": cfg.get("trainRoot"),
            "epochs": cfg.get("epochs"),
            "busy": bool(run and run.status == "running"),
        })

    def post(self, request):
        from apps.flywheel.trainer import run_to_dict, start_train

        try:
            run = start_train(operator=getattr(request.user, "username", "") or "user")
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        return Response({"message": "训练已开始", "run": run_to_dict(run)})


class FlywheelTrainPromoteView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrOperator]

    def post(self, request, pk):
        from apps.flywheel.models import FlywheelTrainRun
        from apps.flywheel.trainer import promote_run, run_to_dict

        run = FlywheelTrainRun.objects.filter(pk=pk).first()
        if not run:
            raise NotFound("训练记录不存在")
        try:
            run = promote_run(run, operator=getattr(request.user, "username", "") or "user")
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        return Response({"message": "已上线新权重", "run": run_to_dict(run)})


class FlywheelTrainRollbackView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrOperator]

    def post(self, request, pk):
        from apps.flywheel.models import FlywheelTrainRun
        from apps.flywheel.trainer import rollback_run, run_to_dict

        run = FlywheelTrainRun.objects.filter(pk=pk).first()
        if not run:
            raise NotFound("训练记录不存在")
        try:
            run = rollback_run(run)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        return Response({"message": run.message, "run": run_to_dict(run)})


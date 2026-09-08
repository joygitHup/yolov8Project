from django.db.models import Count, Exists, OuterRef, Prefetch, Q
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from apps.common.apiview import APIView

from apps.cameras.models import Camera
from apps.common.pagination import paginate_qs
from apps.common.permissions import IsAdminOrOperator
from apps.realtime.broadcast import broadcast
from .models import Alert, AlertAction, AlertTicket
from .serializers import ALERT_LEVELS, ALERT_STATUSES, ALERT_TYPES, AlertSerializer
from . import services


def _start_of_today():
    return timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)


def _alert_qs():
    return (
        Alert.objects.select_related("camera", "ticket")
        .prefetch_related(
            Prefetch("actions", queryset=AlertAction.objects.order_by("-created_at"))
        )
        .annotate(_has_ticket=Exists(AlertTicket.objects.filter(alert_id=OuterRef("pk"))))
    )


def _get_alert(pk):
    alert = _alert_qs().filter(pk=pk).first()
    if not alert:
        raise NotFound("告警不存在")
    return alert


class AlertListView(APIView):
    def get(self, request):
        qs = _alert_qs()

        alert_type = (request.query_params.get("type") or "").strip()
        if alert_type:
            if alert_type not in ALERT_TYPES:
                raise ValidationError("type 无效，可选：intrusion / parking / fire")
            qs = qs.filter(type=alert_type)

        level = (request.query_params.get("level") or "").strip()
        if level:
            if level not in ALERT_LEVELS:
                raise ValidationError("level 无效，可选：high / medium / low")
            qs = qs.filter(level=level)

        status = (request.query_params.get("status") or "").strip()
        if status:
            if status not in ALERT_STATUSES:
                raise ValidationError("status 无效，可选：unhandled / processing / resolved")
            qs = qs.filter(status=status)

        camera_id = (request.query_params.get("cameraId") or "").strip()
        if camera_id:
            try:
                qs = qs.filter(camera_id=int(camera_id))
            except (TypeError, ValueError):
                raise ValidationError("cameraId 必须为整数")

        keyword = (request.query_params.get("keyword") or "").strip()
        if keyword:
            qs = qs.filter(
                Q(description__icontains=keyword)
                | Q(camera_name__icontains=keyword)
                | Q(resolved_note__icontains=keyword)
            )

        start = services.parse_query_dt(request.query_params.get("startDate") or "")
        end = services.parse_query_dt(request.query_params.get("endDate") or "", end=True)
        if start:
            qs = qs.filter(triggered_at__gte=start)
        if end:
            qs = qs.filter(triggered_at__lte=end)

        return Response(paginate_qs(qs, request, AlertSerializer))


class AlertStatsView(APIView):
    def get(self, request):
        from apps.dashboard.services import build_alert_stats

        return Response(build_alert_stats())


class AlertHeatmapView(APIView):
    """Per-camera alert density for map / heatmap widgets."""

    def get(self, request):
        today = _start_of_today()
        qs = Camera.objects.annotate(
            total=Count("alerts", distinct=True),
            today=Count("alerts", filter=Q(alerts__triggered_at__gte=today), distinct=True),
            unhandled=Count("alerts", filter=Q(alerts__status="unhandled"), distinct=True),
            high=Count("alerts", filter=Q(alerts__level="high"), distinct=True),
        ).order_by("-total")
        return Response([
            {
                "cameraId": cam.id,
                "id": cam.id,  # alias
                "name": cam.name,
                "location": cam.location or "",
                "total": cam.total,
                "today": cam.today,
                "unhandled": cam.unhandled,
                "high": cam.high,
            }
            for cam in qs
        ])


def _apply_handle(alert, status, note, operator):
    status = (status or "").strip()
    if status not in ("processing", "resolved"):
        raise ValidationError("status 无效，可选：processing / resolved")
    if alert.status == "resolved":
        raise ValidationError("告警已处理，无法再次变更")
    if alert.status == "processing" and status == "processing":
        # Allow note update while staying in processing
        pass

    from_status = alert.status
    alert.status = status
    note = (note or "").strip()
    if status == "resolved":
        alert.resolved_at = timezone.now()
        alert.resolved_by = getattr(operator, "username", None) or "system"
        alert.resolved_note = note
    elif note:
        alert.resolved_note = note
    alert.save()
    services.log_action(
        alert,
        getattr(operator, "username", None) or "system",
        "handle",
        from_status,
        status,
        note,
    )
    payload = AlertSerializer(alert, context={"detail": True}).data
    broadcast("alert:updated", payload)
    return alert


class AlertDetailView(APIView):
    def get(self, request, pk):
        from apps.alerts import evidence as alert_evidence
        from apps.alerts.jobs import enqueue_evidence

        alert = _get_alert(pk)
        try:
            alert_evidence.reconcile_media_urls(alert)
            alert.refresh_from_db()
        except Exception:
            pass

        snap_ok = (alert.snapshot_url or "").startswith("/media/alerts/")
        vid_ok = (alert.video_url or "").startswith("/media/alerts/")
        if (not snap_ok or not vid_ok) and alert.camera and (alert.camera.rtsp or "").strip():
            try:
                enqueue_evidence(
                    alert.id,
                    alert.camera.rtsp or "",
                    alert.detection_boxes,
                    camera_id=alert.camera_id,
                )
            except Exception:
                pass

        data = AlertSerializer(alert, context={"detail": True}).data
        try:
            data["media"] = alert_evidence.media_status(alert)
        except Exception:
            data["media"] = {
                "snapshotReady": snap_ok,
                "videoReady": vid_ok,
                "pending": not (snap_ok and vid_ok),
                "message": "现场取证采集中…" if not (snap_ok and vid_ok) else "现场取证已就绪",
            }
        return Response(data)


class AlertHandleView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrOperator]

    def post(self, request, pk):
        alert = _get_alert(pk)
        _apply_handle(alert, request.data.get("status"), request.data.get("note"), request.user)
        # Refresh with prefetched relations for consistent detail payload
        alert = _get_alert(pk)
        return Response(AlertSerializer(alert, context={"detail": True}).data)


class AlertBatchHandleView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrOperator]

    def post(self, request):
        ids = request.data.get("ids")
        if not isinstance(ids, list) or not ids:
            raise ValidationError("ids 必须为非空数组")
        status = request.data.get("status")
        note = request.data.get("note")
        cleaned = []
        for item in ids:
            try:
                cleaned.append(int(item))
            except (TypeError, ValueError):
                continue
        if not cleaned:
            raise ValidationError("ids 无效")

        processed = []
        skipped = []
        for pk in cleaned:
            alert = _alert_qs().filter(pk=pk).first()
            if not alert:
                skipped.append({"id": pk, "reason": "not_found"})
                continue
            if alert.status == "resolved":
                skipped.append({"id": pk, "reason": "already_resolved"})
                continue
            _apply_handle(alert, status, note, request.user)
            processed.append(pk)

        return Response({
            "message": f"成功处理 {len(processed)} 条告警",
            "count": len(processed),
            "ids": processed,
            "skipped": skipped,
        })


class AlertEvidenceView(APIView):
    def get(self, request, pk):
        alert = _get_alert(pk)
        svg = services.build_evidence_svg(alert)
        if request.query_params.get("download") == "1" or request.query_params.get("format") == "svg":
            response = HttpResponse(svg, content_type="image/svg+xml")
            response["Content-Disposition"] = f'attachment; filename="alert-{alert.id}.svg"'
            return response
        return Response({
            "id": alert.id,
            "alertId": alert.id,
            "filename": f"alert-{alert.id}.svg",
            "mimeType": "image/svg+xml",
            "content": svg,
            "evidenceUrl": f"/api/alerts/{alert.id}/evidence",
        })


class AlertReportView(APIView):
    def get(self, request, pk):
        alert = _get_alert(pk)
        data = AlertSerializer(alert, context={"detail": True}).data
        boxes = data.get("detectionBoxes") or []
        return Response({
            "title": f"告警报告 #{alert.id}",
            "generatedAt": timezone.localtime().isoformat(),
            "alert": data,
            "summary": {
                "id": alert.id,
                "type": alert.type,
                "level": alert.level,
                "status": alert.status,
                "cameraId": alert.camera_id,
                "cameraName": alert.camera_name,
                "triggeredAt": services.iso(alert.triggered_at),
                "confidence": float(alert.confidence or 0),
                "detectionCount": len(boxes),
            },
        })


class AlertDispatchView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrOperator]

    def post(self, request, pk):
        alert = _get_alert(pk)
        ticket, created = services.create_or_get_ticket(
            alert,
            getattr(request.user, "username", "") or "",
            note=request.data.get("note") or "",
            assignee=request.data.get("assignee") or "",
        )
        alert = _get_alert(pk)
        payload = AlertSerializer(alert, context={"detail": True}).data
        if created:
            broadcast("alert:updated", payload)
        return Response({
            "created": created,
            "message": "工单已派发" if created else "该告警已有工单",
            "ticket": services.serialize_ticket(ticket),
            "alert": payload,
        })

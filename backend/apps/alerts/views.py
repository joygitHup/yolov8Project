from datetime import timedelta

from django.db.models import Count, Q
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cameras.models import Camera
from apps.common.pagination import paginate_qs
from apps.common.permissions import IsAdminOrOperator
from apps.realtime.broadcast import broadcast
from .models import Alert
from .serializers import AlertSerializer
from . import services


def _start_of_today():
    return timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)


def _alert_qs():
    return Alert.objects.select_related("camera")


def _get_alert(pk):
    alert = _alert_qs().filter(pk=pk).first()
    if not alert:
        raise NotFound("告警不存在")
    return alert


class AlertListView(APIView):
    def get(self, request):
        qs = _alert_qs()
        for field in ("type", "level", "status"):
            value = request.query_params.get(field) or ""
            if value:
                qs = qs.filter(**{field: value})
        camera_id = request.query_params.get("cameraId") or ""
        if camera_id:
            qs = qs.filter(camera_id=camera_id)
        keyword = request.query_params.get("keyword") or ""
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
        today = _start_of_today()
        week_start = today - timedelta(days=today.weekday())
        qs = Alert.objects.all()
        status_counts = qs.aggregate(
            total=Count("id"),
            unhandled=Count("id", filter=Q(status="unhandled")),
            processing=Count("id", filter=Q(status="processing")),
            resolved=Count("id", filter=Q(status="resolved")),
            today=Count("id", filter=Q(triggered_at__gte=today)),
            week=Count("id", filter=Q(triggered_at__gte=week_start)),
            intrusion=Count("id", filter=Q(type="intrusion")),
            parking=Count("id", filter=Q(type="parking")),
            fire=Count("id", filter=Q(type="fire")),
            high=Count("id", filter=Q(level="high")),
            medium=Count("id", filter=Q(level="medium")),
            low=Count("id", filter=Q(level="low")),
        )
        cameras = Camera.objects.aggregate(
            total=Count("id"),
            online=Count("id", filter=Q(status="online")),
            offline=Count("id", filter=Q(status="offline")),
        )
        daily = []
        for i in range(6, -1, -1):
            day = today - timedelta(days=i)
            nxt = day + timedelta(days=1)
            row = qs.filter(triggered_at__gte=day, triggered_at__lt=nxt).aggregate(
                total=Count("id"),
                intrusion=Count("id", filter=Q(type="intrusion")),
                parking=Count("id", filter=Q(type="parking")),
                fire=Count("id", filter=Q(type="fire")),
            )
            daily.append({"date": day.date().isoformat(), **row})
        return Response({
            "today": status_counts["today"],
            "week": status_counts["week"],
            "total": status_counts["total"],
            "statusCounts": {
                "unhandled": status_counts["unhandled"],
                "processing": status_counts["processing"],
                "resolved": status_counts["resolved"],
            },
            "typeCounts": {
                "intrusion": status_counts["intrusion"],
                "parking": status_counts["parking"],
                "fire": status_counts["fire"],
            },
            "levelCounts": {
                "high": status_counts["high"],
                "medium": status_counts["medium"],
                "low": status_counts["low"],
            },
            "dailyStats": daily,
            "cameras": cameras,
            "alerts": {
                "today": status_counts["today"],
                "total": status_counts["total"],
                "unhandled": status_counts["unhandled"],
            },
        })


class AlertHeatmapView(APIView):
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
                "id": cam.id,
                "name": cam.name,
                "location": cam.location,
                "total": cam.total,
                "today": cam.today,
                "unhandled": cam.unhandled,
                "high": cam.high,
            }
            for cam in qs
        ])


def _apply_handle(alert, status, note, operator):
    if status not in ("processing", "resolved"):
        raise ValidationError("无效的状态")
    if alert.status == "resolved":
        raise ValidationError("告警已处理")
    from_status = alert.status
    alert.status = status
    if status == "resolved":
        alert.resolved_at = timezone.now()
        alert.resolved_by = getattr(operator, "username", "system")
        alert.resolved_note = note or ""
    elif note:
        alert.resolved_note = note
    alert.save()
    services.log_action(
        alert,
        getattr(operator, "username", "system"),
        "handle",
        from_status,
        status,
        note or "",
    )
    payload = AlertSerializer(alert, context={"detail": True}).data
    broadcast("alert:updated", payload)
    return alert


class AlertDetailView(APIView):
    def get(self, request, pk):
        alert = _get_alert(pk)
        return Response(AlertSerializer(alert, context={"detail": True}).data)


class AlertHandleView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrOperator]

    def post(self, request, pk):
        alert = _get_alert(pk)
        _apply_handle(alert, request.data.get("status"), request.data.get("note"), request.user)
        return Response(AlertSerializer(alert, context={"detail": True}).data)


class AlertBatchHandleView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrOperator]

    def post(self, request):
        ids = request.data.get("ids")
        if not isinstance(ids, list) or not ids:
            raise ValidationError("请选择告警")
        count = 0
        for pk in ids:
            alert = _alert_qs().filter(pk=pk).first()
            if not alert or alert.status == "resolved":
                continue
            _apply_handle(alert, request.data.get("status"), request.data.get("note"), request.user)
            count += 1
        return Response({"message": f"成功处理 {count} 条告警", "count": count})


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
            "filename": f"alert-{alert.id}.svg",
            "mimeType": "image/svg+xml",
            "content": svg,
        })


class AlertReportView(APIView):
    def get(self, request, pk):
        alert = _get_alert(pk)
        data = AlertSerializer(alert, context={"detail": True}).data
        return Response({
            "title": f"告警报告 #{alert.id}",
            "generatedAt": timezone.localtime().isoformat(),
            "alert": data,
            "summary": {
                "type": alert.type,
                "level": alert.level,
                "status": alert.status,
                "camera": alert.camera_name,
                "triggeredAt": services.iso(alert.triggered_at),
                "confidence": alert.confidence,
                "detectionCount": len(alert.detection_boxes or []),
            },
        })


class AlertDispatchView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrOperator]

    def post(self, request, pk):
        alert = _get_alert(pk)
        ticket, created = services.create_or_get_ticket(
            alert,
            getattr(request.user, "username", ""),
            note=request.data.get("note") or "",
            assignee=request.data.get("assignee") or "",
        )
        payload = AlertSerializer(alert, context={"detail": True}).data
        if created:
            broadcast("alert:updated", payload)
        return Response({
            "created": created,
            "message": "工单已派发" if created else "该告警已有工单",
            "ticket": services.serialize_ticket(ticket),
            "alert": payload,
        })

from rest_framework import serializers

from .models import Alert, AlertTicket
from . import services

ALERT_TYPES = {"intrusion", "parking", "fire"}
ALERT_LEVELS = {"high", "medium", "low"}
ALERT_STATUSES = {"unhandled", "processing", "resolved"}


class AlertSerializer(serializers.ModelSerializer):
    """
    Canonical alert fields (camelCase API):

    List + detail:
      id, cameraId, cameraName, cameraLocation, cameraIp, cameraStatus,
      type, level, description, confidence, status,
      snapshotUrl, imageUrl, videoUrl, evidenceUrl,
      detectionBoxes[{id,label,confidence,bbox:{x,y,w,h}}],
      detectionCount, triggeredAt, resolvedBy, resolvedAt, resolvedNote,
      hasTicket, createdAt, updatedAt

    Detail only (context.detail=True):
      camera{}, clip{}, ticket{}, actions[], evidenceSvg
    """

    cameraId = serializers.IntegerField(source="camera_id", allow_null=True, read_only=True)
    cameraName = serializers.CharField(source="camera_name")
    snapshotUrl = serializers.CharField(source="snapshot_url", required=False, allow_blank=True)
    imageUrl = serializers.CharField(source="image_url", required=False, allow_blank=True)
    videoUrl = serializers.CharField(source="video_url", required=False, allow_blank=True)
    detectionBoxes = serializers.JSONField(source="detection_boxes", required=False)
    triggeredAt = serializers.DateTimeField(source="triggered_at")
    resolvedBy = serializers.CharField(source="resolved_by", required=False, allow_blank=True)
    resolvedAt = serializers.DateTimeField(source="resolved_at", allow_null=True, required=False)
    resolvedNote = serializers.CharField(source="resolved_note", required=False, allow_blank=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)
    evidenceUrl = serializers.SerializerMethodField()
    detectionCount = serializers.SerializerMethodField()
    hasTicket = serializers.SerializerMethodField()

    class Meta:
        model = Alert
        fields = [
            "id",
            "cameraId",
            "cameraName",
            "type",
            "level",
            "description",
            "confidence",
            "status",
            "snapshotUrl",
            "imageUrl",
            "videoUrl",
            "evidenceUrl",
            "detectionBoxes",
            "detectionCount",
            "triggeredAt",
            "resolvedBy",
            "resolvedAt",
            "resolvedNote",
            "hasTicket",
            "createdAt",
            "updatedAt",
        ]
        read_only_fields = [
            "id",
            "cameraId",
            "evidenceUrl",
            "detectionCount",
            "hasTicket",
            "createdAt",
            "updatedAt",
        ]

    def get_evidenceUrl(self, obj):
        return f"/api/alerts/{obj.id}/evidence"

    def get_detectionCount(self, obj):
        return len(obj.detection_boxes or [])

    def get_hasTicket(self, obj):
        annotated = getattr(obj, "_has_ticket", None)
        if annotated is not None:
            return bool(annotated)
        if hasattr(obj, "ticket"):
            try:
                return obj.ticket is not None
            except AlertTicket.DoesNotExist:
                return False
        return AlertTicket.objects.filter(alert_id=obj.id).exists()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        camera = instance.camera
        evidence = f"/api/alerts/{instance.id}/evidence"

        data["cameraName"] = data.get("cameraName") or (camera.name if camera else "") or ""
        data["cameraLocation"] = (camera.location if camera else "") or ""
        data["cameraIp"] = (camera.ip if camera else "") or ""
        data["cameraStatus"] = (camera.status if camera else "") or ""
        data["confidence"] = float(data.get("confidence") or 0)
        data["detectionBoxes"] = services.normalize_detection_boxes(instance.detection_boxes)
        data["detectionCount"] = len(data["detectionBoxes"])

        # Media URLs: prefer stored real files; fall back to SVG evidence endpoint
        snapshot = (data.get("snapshotUrl") or "").strip()
        has_real_snap = snapshot.startswith("/media/alerts/")
        has_real_video = (data.get("videoUrl") or "").strip().startswith("/media/alerts/")
        if not snapshot:
            snapshot = evidence
        data["snapshotUrl"] = snapshot
        data["imageUrl"] = (data.get("imageUrl") or "").strip() or snapshot
        data["videoUrl"] = (data.get("videoUrl") or "").strip()
        data["evidenceUrl"] = evidence
        data["hasTicket"] = bool(data.get("hasTicket"))
        data["hasRealMedia"] = has_real_snap or has_real_video

        if self.context.get("detail"):
            ticket = None
            try:
                ticket = instance.ticket
            except AlertTicket.DoesNotExist:
                ticket = None
            actions = list(instance.actions.all()[:30])
            data["camera"] = services.serialize_camera(camera)
            data["clip"] = services.build_clip(instance)
            data["ticket"] = services.serialize_ticket(ticket)
            data["actions"] = [services.serialize_action(item) for item in actions]
            # SVG only as fallback when no real snapshot yet
            data["evidenceSvg"] = "" if has_real_snap else services.build_evidence_svg(instance)
            if not has_real_snap and snapshot.startswith("/api/alerts/"):
                data["snapshotUrl"] = evidence
                data["imageUrl"] = evidence
            data["hasTicket"] = ticket is not None

        return data

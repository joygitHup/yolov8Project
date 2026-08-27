from rest_framework import serializers
from .models import Alert, AlertTicket
from . import services


class AlertSerializer(serializers.ModelSerializer):
    cameraId = serializers.IntegerField(source="camera_id", allow_null=True, read_only=True)
    cameraName = serializers.CharField(source="camera_name")
    snapshotUrl = serializers.CharField(source="snapshot_url", required=False)
    imageUrl = serializers.CharField(source="image_url", required=False)
    videoUrl = serializers.CharField(source="video_url", required=False)
    detectionBoxes = serializers.JSONField(source="detection_boxes", required=False)
    triggeredAt = serializers.DateTimeField(source="triggered_at")
    resolvedBy = serializers.CharField(source="resolved_by", required=False, allow_blank=True)
    resolvedAt = serializers.DateTimeField(source="resolved_at", allow_null=True, required=False)
    resolvedNote = serializers.CharField(source="resolved_note", required=False, allow_blank=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)

    class Meta:
        model = Alert
        fields = [
            "id", "cameraId", "cameraName", "type", "level", "description", "confidence",
            "status", "snapshotUrl", "imageUrl", "videoUrl", "detectionBoxes",
            "triggeredAt", "resolvedBy", "resolvedAt", "resolvedNote", "createdAt", "updatedAt",
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        camera = instance.camera
        data["cameraLocation"] = camera.location if camera else ""
        data["cameraIp"] = camera.ip if camera else ""
        data["cameraStatus"] = camera.status if camera else ""
        if self.context.get("detail"):
            ticket = AlertTicket.objects.filter(alert=instance).first()
            actions = list(instance.actions.all()[:20])
            data["camera"] = services.serialize_camera(camera)
            data["clip"] = services.build_clip(instance)
            data["ticket"] = services.serialize_ticket(ticket)
            data["actions"] = [services.serialize_action(item) for item in actions]
            data["evidenceSvg"] = services.build_evidence_svg(instance)
            data["snapshotUrl"] = f"/api/alerts/{instance.id}/evidence"
            data["imageUrl"] = data["snapshotUrl"]
        return data

from rest_framework import serializers
from apps.cameras.models import Camera
from .models import Strategy


class StrategySerializer(serializers.ModelSerializer):
    cameraIds = serializers.JSONField(source="camera_ids")
    detectionTypes = serializers.JSONField(source="detection_types")
    alertLevel = serializers.CharField(source="alert_level", required=False)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)
    cameraNames = serializers.SerializerMethodField()

    class Meta:
        model = Strategy
        fields = [
            "id", "name", "cameraIds", "detectionTypes", "schedule",
            "alertLevel", "enabled", "cameraNames", "createdAt", "updatedAt",
        ]

    def get_cameraNames(self, obj):
        names = dict(Camera.objects.filter(id__in=obj.camera_ids or []).values_list("id", "name"))
        return [names.get(cid) for cid in (obj.camera_ids or []) if cid in names]

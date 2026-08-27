from rest_framework import serializers
from .models import Camera


class CameraSerializer(serializers.ModelSerializer):
    detectionTypes = serializers.JSONField(source="detection_types", required=False)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)

    class Meta:
        model = Camera
        fields = [
            "id", "name", "location", "ip", "rtsp", "type", "username", "password",
            "resolution", "channels", "status", "enabled", "detectionTypes",
            "createdAt", "updatedAt",
        ]


class CameraOptionSerializer(serializers.ModelSerializer):
    detectionTypes = serializers.JSONField(source="detection_types", required=False)

    class Meta:
        model = Camera
        fields = [
            "id", "name", "status", "location", "enabled", "type",
            "ip", "rtsp", "resolution", "channels", "detectionTypes",
        ]

from rest_framework import serializers
from .models import Camera

CAMERA_TYPES = {"hikvision", "dahua", "other"}
CAMERA_STATUSES = {"online", "offline"}
DETECTION_TYPES = {"intrusion", "parking", "fire"}


class CameraHealthListSerializer(serializers.ListSerializer):
    def to_representation(self, data):
        from apps.common import rdb

        self.child._batch_streams = rdb.get_all_stream_health()
        try:
            return super().to_representation(data)
        finally:
            self.child._batch_streams = None


class CameraSerializer(serializers.ModelSerializer):
    """
    Canonical camera management fields (camelCase API):
      id, name, location, ip, rtsp, type, username,
      password (writeOnly), resolution, channels,
      status (online|offline), enabled, live (readOnly),
      detectionTypes[], createdAt, updatedAt
    """

    detectionTypes = serializers.JSONField(source="detection_types", required=False)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)
    password = serializers.CharField(required=False, allow_blank=True, write_only=True)
    live = serializers.SerializerMethodField()

    class Meta:
        model = Camera
        fields = [
            "id",
            "name",
            "location",
            "ip",
            "rtsp",
            "type",
            "username",
            "password",
            "resolution",
            "channels",
            "status",
            "enabled",
            "live",
            "detectionTypes",
            "createdAt",
            "updatedAt",
        ]
        read_only_fields = ["id", "createdAt", "updatedAt", "live"]
        list_serializer_class = CameraHealthListSerializer

    def get_live(self, obj):
        return bool(obj.enabled and obj.status == "online" and (obj.rtsp or "").strip())

    def validate_type(self, value):
        value = (value or "hikvision").strip()
        if value not in CAMERA_TYPES:
            raise serializers.ValidationError("设备类型无效，可选：hikvision / dahua / other")
        return value

    def validate_status(self, value):
        value = (value or "online").strip()
        if value not in CAMERA_STATUSES:
            raise serializers.ValidationError("状态无效，可选：online / offline")
        return value

    def validate_detectionTypes(self, value):
        if value is None:
            return ["intrusion", "parking", "fire"]
        if not isinstance(value, list):
            raise serializers.ValidationError("detectionTypes 必须为数组")
        cleaned = []
        for item in value:
            key = str(item).strip()
            if key not in DETECTION_TYPES:
                raise serializers.ValidationError(f"检测类型无效: {key}")
            if key not in cleaned:
                cleaned.append(key)
        return cleaned or ["intrusion", "parking", "fire"]

    def validate_channels(self, value):
        try:
            n = int(value)
        except (TypeError, ValueError):
            raise serializers.ValidationError("通道数必须为整数")
        if n < 1 or n > 64:
            raise serializers.ValidationError("通道数范围为 1~64")
        return n

    def validate_name(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("名称不能为空")
        return value

    def validate_rtsp(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("RTSP 地址不能为空")
        return value

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Always expose array; never null
        data["detectionTypes"] = data.get("detectionTypes") or []
        data["location"] = data.get("location") or ""
        data["ip"] = data.get("ip") or ""
        data["username"] = data.get("username") or ""
        data["resolution"] = data.get("resolution") or "1920x1080"
        data["enabled"] = bool(data.get("enabled"))
        from apps.cameras.health import camera_health

        streams = getattr(self, "_batch_streams", None)
        if streams is None:
            streams = self.context.get("streams")
        health = camera_health(instance, streams=streams)
        data.update(health)
        # password never returned
        data.pop("password", None)
        return data

    def create(self, validated_data):
        if "detection_types" not in validated_data:
            validated_data["detection_types"] = ["intrusion", "parking", "fire"]
        if not validated_data.get("username"):
            validated_data["username"] = "admin"
        if not validated_data.get("status"):
            validated_data["status"] = "offline"
        if "enabled" not in validated_data:
            validated_data["enabled"] = True
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # Empty password means "keep unchanged"
        if "password" in validated_data and validated_data.get("password") == "":
            validated_data.pop("password")
        return super().update(instance, validated_data)


class CameraOptionSerializer(serializers.ModelSerializer):
    """Lightweight option list for selectors (no credentials)."""

    detectionTypes = serializers.JSONField(source="detection_types", required=False)
    live = serializers.SerializerMethodField()

    class Meta:
        model = Camera
        fields = [
            "id",
            "name",
            "status",
            "location",
            "enabled",
            "live",
            "type",
            "ip",
            "resolution",
            "channels",
            "detectionTypes",
        ]
        list_serializer_class = CameraHealthListSerializer

    def get_live(self, obj):
        return bool(obj.enabled and obj.status == "online" and (obj.rtsp or "").strip())

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["detectionTypes"] = data.get("detectionTypes") or []
        from apps.cameras.health import camera_health

        streams = getattr(self, "_batch_streams", None)
        if streams is None:
            streams = self.context.get("streams")
        data.update(camera_health(instance, streams=streams))
        return data

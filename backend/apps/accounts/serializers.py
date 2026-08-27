from rest_framework import serializers
from .models import User


class UserSerializer(serializers.ModelSerializer):
    realName = serializers.CharField(source="name", required=False, allow_blank=True)
    enabled = serializers.BooleanField(source="is_active", required=False)
    status = serializers.SerializerMethodField()
    lastLoginAt = serializers.DateTimeField(source="last_login", read_only=True, allow_null=True)
    createdAt = serializers.DateTimeField(source="date_joined", read_only=True)
    updatedAt = serializers.DateTimeField(source="date_joined", read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "username", "name", "realName", "role", "email", "phone", "avatar",
            "enabled", "status", "lastLoginAt", "createdAt", "updatedAt",
        ]
        read_only_fields = ["id", "username"]

    def get_status(self, obj):
        return "active" if obj.is_active else "disabled"

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["name"] = instance.name or instance.username
        data["realName"] = instance.name or instance.username
        return data


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()


class PasswordSerializer(serializers.Serializer):
    oldPassword = serializers.CharField()
    newPassword = serializers.CharField()

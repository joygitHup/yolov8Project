from django.db import models


class SystemSetting(models.Model):
    key = models.CharField(max_length=64, unique=True)
    value = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "config"


class Strategy(models.Model):
    name = models.CharField(max_length=128)
    camera_ids = models.JSONField(default=list)
    detection_types = models.JSONField(default=list)
    schedule = models.JSONField(default=dict)
    alert_level = models.CharField(max_length=16, default="medium")
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "strategies"
        ordering = ["-id"]


class NotificationLog(models.Model):
    channel = models.CharField(max_length=32)
    kind = models.CharField(max_length=16, default="alert")
    success = models.BooleanField(default=False)
    message = models.CharField(max_length=255, blank=True, default="")
    alert_id = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notification_logs"
        ordering = ["-id"]

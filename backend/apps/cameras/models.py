from django.db import models


class Camera(models.Model):
    TYPE_CHOICES = (("hikvision", "海康威视"), ("dahua", "大华"), ("other", "其他"))
    STATUS_CHOICES = (("online", "在线"), ("offline", "离线"))

    name = models.CharField(max_length=128)
    location = models.CharField(max_length=128, blank=True, default="")
    ip = models.CharField(max_length=64, blank=True, default="")
    rtsp = models.CharField(max_length=255)
    type = models.CharField(max_length=32, choices=TYPE_CHOICES, default="hikvision")
    username = models.CharField(max_length=64, blank=True, default="admin")
    password = models.CharField(max_length=128, blank=True, default="")
    resolution = models.CharField(max_length=32, default="1920x1080")
    channels = models.IntegerField(default=1)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="offline")
    enabled = models.BooleanField(default=True)
    detection_types = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "cameras"
        ordering = ["-id"]


class CameraRuntimeState(models.Model):
    camera = models.OneToOneField(Camera, on_delete=models.CASCADE, related_name="runtime")
    pan = models.FloatField(default=0)
    tilt = models.FloatField(default=0)
    zoom = models.FloatField(default=1)
    last_direction = models.CharField(max_length=16, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "camera_runtime_state"


class CameraSnapshot(models.Model):
    camera = models.ForeignKey(Camera, on_delete=models.CASCADE, related_name="snapshots")
    operator = models.CharField(max_length=64, blank=True, default="")
    detections = models.JSONField(default=list)
    detection_count = models.IntegerField(default=0)
    fps = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "camera_snapshots"
        ordering = ["-id"]


class CameraRecording(models.Model):
    STATUS_CHOICES = (("recording", "录制中"), ("stopped", "已停止"))

    camera = models.ForeignKey(Camera, on_delete=models.CASCADE, related_name="recordings")
    operator = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="recording")
    started_at = models.DateTimeField(auto_now_add=True)
    stopped_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "camera_recordings"
        ordering = ["-id"]

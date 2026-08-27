from django.db import models


class Alert(models.Model):
    TYPE_CHOICES = (("intrusion", "区域入侵"), ("parking", "违停占道"), ("fire", "火灾隐患"))
    LEVEL_CHOICES = (("high", "高危"), ("medium", "中危"), ("low", "低危"))
    STATUS_CHOICES = (("unhandled", "待处理"), ("processing", "处理中"), ("resolved", "已处理"))

    camera = models.ForeignKey("cameras.Camera", null=True, on_delete=models.SET_NULL, related_name="alerts")
    camera_name = models.CharField(max_length=128, blank=True, default="")
    type = models.CharField(max_length=32, choices=TYPE_CHOICES)
    level = models.CharField(max_length=16, choices=LEVEL_CHOICES, default="medium")
    description = models.CharField(max_length=255)
    confidence = models.FloatField(default=0.8)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="unhandled")
    snapshot_url = models.CharField(max_length=255, blank=True, default="")
    image_url = models.CharField(max_length=255, blank=True, default="")
    video_url = models.CharField(max_length=255, blank=True, default="")
    detection_boxes = models.JSONField(default=list)
    triggered_at = models.DateTimeField()
    resolved_by = models.CharField(max_length=64, blank=True, default="")
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_note = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "alerts"
        ordering = ["-triggered_at"]


class AlertAction(models.Model):
    alert = models.ForeignKey(Alert, on_delete=models.CASCADE, related_name="actions")
    operator = models.CharField(max_length=64, blank=True, default="")
    action = models.CharField(max_length=32, default="handle")
    from_status = models.CharField(max_length=16, blank=True, default="")
    to_status = models.CharField(max_length=16, blank=True, default="")
    note = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "alert_actions"
        ordering = ["-created_at"]


class AlertTicket(models.Model):
    STATUS_CHOICES = (("open", "待处理"), ("done", "已完成"))

    alert = models.OneToOneField(Alert, on_delete=models.CASCADE, related_name="ticket")
    title = models.CharField(max_length=255)
    assignee = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="open")
    note = models.CharField(max_length=255, blank=True, default="")
    created_by = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "alert_tickets"
        ordering = ["-id"]

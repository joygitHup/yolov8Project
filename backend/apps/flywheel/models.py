from django.db import models


class FlywheelSample(models.Model):
    SOURCE_CHOICES = (("alert", "告警帧"), ("uncertain", "不确定帧"))
    STATUS_CHOICES = (
        ("pending", "待审核"),
        ("approved", "已通过"),
        ("discarded", "已丢弃"),
    )

    camera_id = models.IntegerField(db_index=True)
    source = models.CharField(max_length=16, choices=SOURCE_CHOICES, db_index=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending", db_index=True)
    alert_id = models.IntegerField(null=True, blank=True)
    stem = models.CharField(max_length=128, unique=True)
    image_key = models.CharField(max_length=255)
    label_key = models.CharField(max_length=255)
    reviewed_image_key = models.CharField(max_length=255, blank=True, default="")
    reviewed_label_key = models.CharField(max_length=255, blank=True, default="")
    boxes = models.JSONField(default=list)
    max_conf = models.FloatField(default=0)
    box_count = models.IntegerField(default=0)
    reviewed_by = models.CharField(max_length=64, blank=True, default="")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "flywheel_samples"
        ordering = ["id"]


class FlywheelTrainRun(models.Model):
    STATUS_CHOICES = (
        ("queued", "排队中"),
        ("running", "训练中"),
        ("promoted", "已上线"),
        ("rejected", "未上线"),
        ("failed", "失败"),
    )

    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="queued", db_index=True)
    operator = models.CharField(max_length=64, blank=True, default="")
    reviewed_count = models.IntegerField(default=0)
    exported = models.IntegerField(default=0)
    epochs = models.IntegerField(default=15)
    base_weights = models.CharField(max_length=512, blank=True, default="")
    new_weights = models.CharField(max_length=512, blank=True, default="")
    previous_weights = models.CharField(max_length=512, blank=True, default="")
    old_map50 = models.FloatField(null=True, blank=True)
    new_map50 = models.FloatField(null=True, blank=True)
    promoted = models.BooleanField(default=False)
    message = models.CharField(max_length=512, blank=True, default="")
    log = models.TextField(blank=True, default="")
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "flywheel_train_runs"
        ordering = ["-id"]


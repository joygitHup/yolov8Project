from django.db import models


class DetectionMetric(models.Model):
    """按日汇总的真实推理计数，供数据大屏使用。"""
    date = models.DateField(db_index=True)
    camera = models.ForeignKey(
        "cameras.Camera",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="detection_metrics",
    )
    frame_count = models.PositiveIntegerField(default=0)
    box_count = models.PositiveIntegerField(default=0)
    confidence_sum = models.FloatField(default=0)

    class Meta:
        db_table = "detection_metrics"
        unique_together = ("date", "camera")
        ordering = ["-date"]

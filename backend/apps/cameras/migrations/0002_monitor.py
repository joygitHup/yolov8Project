from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("cameras", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CameraRuntimeState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("pan", models.FloatField(default=0)),
                ("tilt", models.FloatField(default=0)),
                ("zoom", models.FloatField(default=1)),
                ("last_direction", models.CharField(blank=True, default="", max_length=16)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "camera",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="runtime",
                        to="cameras.camera",
                    ),
                ),
            ],
            options={"db_table": "camera_runtime_state"},
        ),
        migrations.CreateModel(
            name="CameraSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("operator", models.CharField(blank=True, default="", max_length=64)),
                ("detections", models.JSONField(default=list)),
                ("detection_count", models.IntegerField(default=0)),
                ("fps", models.FloatField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "camera",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="snapshots",
                        to="cameras.camera",
                    ),
                ),
            ],
            options={"db_table": "camera_snapshots", "ordering": ["-id"]},
        ),
        migrations.CreateModel(
            name="CameraRecording",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("operator", models.CharField(blank=True, default="", max_length=64)),
                (
                    "status",
                    models.CharField(
                        choices=[("recording", "录制中"), ("stopped", "已停止")],
                        default="recording",
                        max_length=16,
                    ),
                ),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("stopped_at", models.DateTimeField(blank=True, null=True)),
                (
                    "camera",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="recordings",
                        to="cameras.camera",
                    ),
                ),
            ],
            options={"db_table": "camera_recordings", "ordering": ["-id"]},
        ),
    ]

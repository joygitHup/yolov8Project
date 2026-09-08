from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("flywheel", "0002_review_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="FlywheelTrainRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("running", "训练中"),
                            ("promoted", "已上线"),
                            ("rejected", "未上线"),
                            ("failed", "失败"),
                        ],
                        db_index=True,
                        default="running",
                        max_length=16,
                    ),
                ),
                ("operator", models.CharField(blank=True, default="", max_length=64)),
                ("reviewed_count", models.IntegerField(default=0)),
                ("exported", models.IntegerField(default=0)),
                ("epochs", models.IntegerField(default=15)),
                ("base_weights", models.CharField(blank=True, default="", max_length=512)),
                ("new_weights", models.CharField(blank=True, default="", max_length=512)),
                ("previous_weights", models.CharField(blank=True, default="", max_length=512)),
                ("old_map50", models.FloatField(blank=True, null=True)),
                ("new_map50", models.FloatField(blank=True, null=True)),
                ("promoted", models.BooleanField(default=False)),
                ("message", models.CharField(blank=True, default="", max_length=512)),
                ("log", models.TextField(blank=True, default="")),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "db_table": "flywheel_train_runs",
                "ordering": ["-id"],
            },
        ),
    ]

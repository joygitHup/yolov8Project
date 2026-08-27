from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("alerts", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AlertAction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("operator", models.CharField(blank=True, default="", max_length=64)),
                ("action", models.CharField(default="handle", max_length=32)),
                ("from_status", models.CharField(blank=True, default="", max_length=16)),
                ("to_status", models.CharField(blank=True, default="", max_length=16)),
                ("note", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "alert",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="actions",
                        to="alerts.alert",
                    ),
                ),
            ],
            options={"db_table": "alert_actions", "ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="AlertTicket",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255)),
                ("assignee", models.CharField(blank=True, default="", max_length=64)),
                (
                    "status",
                    models.CharField(
                        choices=[("open", "待处理"), ("done", "已完成")],
                        default="open",
                        max_length=16,
                    ),
                ),
                ("note", models.CharField(blank=True, default="", max_length=255)),
                ("created_by", models.CharField(blank=True, default="", max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "alert",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ticket",
                        to="alerts.alert",
                    ),
                ),
            ],
            options={"db_table": "alert_tickets", "ordering": ["-id"]},
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("systemcfg", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="NotificationLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("channel", models.CharField(max_length=32)),
                ("kind", models.CharField(default="alert", max_length=16)),
                ("success", models.BooleanField(default=False)),
                ("message", models.CharField(blank=True, default="", max_length=255)),
                ("alert_id", models.IntegerField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"db_table": "notification_logs", "ordering": ["-id"]},
        ),
    ]

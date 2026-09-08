from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cameras", "0002_monitor"),
    ]

    operations = [
        migrations.AlterField(
            model_name="camera",
            name="status",
            field=models.CharField(
                choices=[("online", "在线"), ("offline", "离线")],
                default="offline",
                max_length=16,
            ),
        ),
    ]

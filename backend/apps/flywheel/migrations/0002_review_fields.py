from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("flywheel", "0001_flywheel_samples"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="flywheelsample",
            options={"ordering": ["id"]},
        ),
        migrations.AddField(
            model_name="flywheelsample",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "待审核"),
                    ("approved", "已通过"),
                    ("discarded", "已丢弃"),
                ],
                db_index=True,
                default="pending",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="flywheelsample",
            name="boxes",
            field=models.JSONField(default=list),
        ),
        migrations.AddField(
            model_name="flywheelsample",
            name="reviewed_image_key",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="flywheelsample",
            name="reviewed_label_key",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="flywheelsample",
            name="reviewed_by",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="flywheelsample",
            name="reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

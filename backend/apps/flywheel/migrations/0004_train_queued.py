from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("flywheel", "0003_train_runs"),
    ]

    operations = [
        migrations.AlterField(
            model_name="flywheeltrainrun",
            name="status",
            field=models.CharField(
                choices=[
                    ("queued", "排队中"),
                    ("running", "训练中"),
                    ("promoted", "已上线"),
                    ("rejected", "未上线"),
                    ("failed", "失败"),
                ],
                db_index=True,
                default="queued",
                max_length=16,
            ),
        ),
    ]

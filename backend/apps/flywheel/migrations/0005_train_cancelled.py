from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("flywheel", "0004_train_queued"),
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
                    ("cancelled", "已取消"),
                ],
                db_index=True,
                default="queued",
                max_length=16,
            ),
        ),
    ]

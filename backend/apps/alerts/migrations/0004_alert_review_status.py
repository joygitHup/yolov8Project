from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("alerts", "0003_alter_alert_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="alert",
            name="status",
            field=models.CharField(
                choices=[
                    ("unhandled", "待处理"),
                    ("processing", "处理中"),
                    ("resolved", "已处理"),
                    ("review", "待确认"),
                ],
                default="unhandled",
                max_length=16,
            ),
        ),
    ]

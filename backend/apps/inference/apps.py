import os
import sys
from django.apps import AppConfig


class InferenceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.inference"
    label = "inference"

    def ready(self):
        if "migrate" in sys.argv or "makemigrations" in sys.argv:
            return
        if os.environ.get("RUN_MAIN") != "true":
            return
        from apps.inference.pipeline import start_pipeline
        start_pipeline()

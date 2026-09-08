import os
import sys
import threading
from django.apps import AppConfig


class InferenceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.inference"
    label = "inference"

    def ready(self):
        from apps.common.process import django_embeds_runtime, is_mgmt_skip

        if is_mgmt_skip() or not django_embeds_runtime():
            return
        using_reloader = "runserver" in sys.argv and "--noreload" not in sys.argv
        if using_reloader and os.environ.get("RUN_MAIN") != "true":
            return

        def _start():
            from apps.inference.pipeline import start_pipeline
            start_pipeline()

        threading.Timer(1.0, _start).start()

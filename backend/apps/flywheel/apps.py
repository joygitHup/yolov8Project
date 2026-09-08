from django.apps import AppConfig


class FlywheelConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.flywheel"
    label = "flywheel"

    def ready(self):
        import os
        import sys
        import threading

        from apps.common.process import is_mgmt_skip

        if is_mgmt_skip():
            return
        using_reloader = "runserver" in sys.argv and "--noreload" not in sys.argv
        if using_reloader and os.environ.get("RUN_MAIN") != "true":
            return

        def _repair():
            try:
                from apps.flywheel.relabel import repair_mislabelled_samples

                repair_mislabelled_samples(force=False)
            except Exception:
                pass

        threading.Timer(8.0, _repair).start()

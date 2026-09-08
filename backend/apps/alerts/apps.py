from django.apps import AppConfig


class AlertsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.alerts"
    label = "alerts"

    def ready(self):
        import os
        import threading

        from apps.common.process import django_embeds_runtime, is_mgmt_skip

        if is_mgmt_skip() or not django_embeds_runtime():
            return
        using_reloader = "runserver" in __import__("sys").argv and "--noreload" not in __import__("sys").argv
        if using_reloader and os.environ.get("RUN_MAIN") != "true":
            return

        def _start():
            try:
                from apps.common.jobs import start_embedded_workers
                from apps.common.storage import ping as minio_ping

                status = minio_ping()
                print(f"[alerts] evidence backend={status.get('backend')} minio_ok={status.get('ok')}")
                start_embedded_workers()
            except Exception as exc:
                print(f"[alerts] job worker skipped: {exc}")

        threading.Timer(1.2, _start).start()

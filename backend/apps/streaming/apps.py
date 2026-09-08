from django.apps import AppConfig


class StreamingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.streaming"
    label = "streaming"

    def ready(self):
        import atexit
        import threading

        from apps.common.process import django_embeds_runtime, is_mgmt_skip
        from apps.streaming.manager import stream_manager

        if is_mgmt_skip() or not django_embeds_runtime():
            return

        atexit.register(stream_manager.stop_all)

        def _bootstrap_demo():
            try:
                from apps.streaming.publisher import demo_publish_enabled, demo_publisher, wire_cameras_to_demo_rtsp

                updated, total = wire_cameras_to_demo_rtsp()
                ok = demo_publisher.ensure_started()
                mode = "on" if ok else ("off" if not demo_publish_enabled() else "off (fallback)")
                print(
                    f"[streaming] demo RTSP cameras={updated}/{total} updated, "
                    f"publisher={mode}"
                )
            except Exception as exc:
                print(f"[streaming] demo bootstrap skipped: {exc}")

        threading.Timer(1.5, _bootstrap_demo).start()

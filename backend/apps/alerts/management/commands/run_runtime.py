from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Run orchestrator outside Django HTTP: YOLO camera sync, "
        "ffmpeg/MediaMTX publish, snapshot/clip/flywheel jobs, training."
    )

    def handle(self, *args, **options):
        import sys

        sys.stdout.write("runtime command starting\n")
        sys.stdout.flush()
        from django.conf import settings

        from apps.common.process import enable_sqlite_wal

        settings.JOBS_EMBEDDED = True
        enable_sqlite_wal()
        self.stdout.write(
            f"runtime starting REDIS_URL={settings.REDIS_URL} "
            f"JOBS_BACKEND={getattr(settings, 'JOBS_BACKEND', 'rabbitmq')} "
            f"KAFKA={getattr(settings, 'KAFKA_BOOTSTRAP', '')} "
            f"YOLO_INFER_MODE={__import__('os').environ.get('YOLO_INFER_MODE', 'remote')}"
        )
        from apps.common.runtime import run_forever

        run_forever()

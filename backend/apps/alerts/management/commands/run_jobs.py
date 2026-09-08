from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run job workers (RabbitMQ by default). Use when JOBS_EMBEDDED=0."

    def handle(self, *args, **options):
        from django.conf import settings

        settings.JOBS_EMBEDDED = True
        self.stdout.write(
            f"job workers starting backend={getattr(settings, 'JOBS_BACKEND', 'rabbitmq')} "
            f"RABBITMQ_URL={getattr(settings, 'RABBITMQ_URL', '')}"
        )
        from apps.common.jobs import run_forever

        run_forever()

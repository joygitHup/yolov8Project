#!/usr/bin/env python
"""Start Django (migrate + seed + ASGI runserver)."""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


def resolve_port():
    if os.environ.get("BACKEND_PORT"):
        return int(os.environ["BACKEND_PORT"])
    base = int(os.environ.get("DEPLOY_RUN_PORT", "5000"))
    if os.environ.get("COZE_PROJECT_ENV") == "PROD" or os.environ.get("NODE_ENV") == "production":
        return base
    return base + 1


def main():
    import django
    from django.core.management import call_command

    django.setup()
    call_command("migrate", interactive=False, verbosity=1)
    from apps.common.seed import seed_if_empty
    seed_if_empty()

    port = resolve_port()
    print(f"Django DRF 后端启动  http://localhost:{port}/api")
    print(f"WebSocket            ws://localhost:{port}/ws")
    call_command("runserver", f"0.0.0.0:{port}")


if __name__ == "__main__":
    main()

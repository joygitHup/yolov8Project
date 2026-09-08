#!/usr/bin/env python
"""Start Django (migrate + seed + ASGI runserver)."""
import os
import sys
from pathlib import Path

# Daphne default executor + Django thread-sensitive pool. Sync views still exist;
# cheap Redis health + async WebSocket keep one slow HTTP from stalling WS.
os.environ.setdefault("ASGI_THREADS", "16")
os.environ.setdefault("DJANGO_ASGI_THREADS", "16")

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
    from django.conf import settings
    from apps.common.process import enable_sqlite_wal

    engine = (settings.DATABASES.get("default") or {}).get("ENGINE") or ""
    if engine.endswith("sqlite3"):
        enable_sqlite_wal()
    call_command("migrate", interactive=False, verbosity=1)
    from apps.common.seed import seed_if_empty
    seed_if_empty()

    port = resolve_port()
    print(f"Django DRF 后端启动  http://localhost:{port}/api")
    print(f"WebSocket            ws://localhost:{port}/ws")
    print(f"DB                   {engine} {settings.DATABASES['default'].get('HOST') or settings.DATABASES['default'].get('NAME')}")
    args = [f"0.0.0.0:{port}"]
    reload_on = os.environ.get("DJANGO_RELOAD", "").strip().lower() in ("1", "true", "yes", "on")
    if not reload_on:
        args.append("--noreload")
    call_command("runserver", *args)


if __name__ == "__main__":
    main()

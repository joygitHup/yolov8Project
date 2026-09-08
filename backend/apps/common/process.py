"""Which process should run orchestrator / jobs / ffmpeg."""
from __future__ import annotations

import os
import sys


def is_mgmt_skip() -> bool:
    argv = " ".join(sys.argv)
    for token in ("migrate", "makemigrations", "run_jobs", "run_runtime"):
        if token in argv:
            return True
    return False


def django_embeds_runtime() -> bool:
    raw = (os.environ.get("DJANGO_EMBEDDED_RUNTIME") or "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


def is_runtime_process() -> bool:
    """True in `manage.py run_runtime`, or when Django still embeds the orchestrator."""
    if "run_runtime" in " ".join(sys.argv):
        return True
    return django_embeds_runtime()


def enable_sqlite_wal() -> None:
    from django.db import connection

    if connection.vendor != "sqlite":
        return
    cursor = connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA busy_timeout=20000;")

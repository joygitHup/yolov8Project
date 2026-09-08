"""Shared secret for yolo-service HTTP API."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import Header, HTTPException

_HEADER = "X-Ingest-Token"


def service_token() -> str:
    env = (os.environ.get("YOLO_SERVICE_TOKEN") or os.environ.get("INGEST_TOKEN") or "").strip()
    if env:
        return env
    extra = (os.environ.get("INGEST_TOKEN_FILE") or "").strip()
    candidates = [Path(p) for p in (extra,) if p]
    here = Path(__file__).resolve()
    candidates.append(here.parents[2] / "backend" / "data" / ".ingest_token")
    for path in candidates:
        try:
            if path.is_file():
                text = path.read_text(encoding="utf-8").strip()
                if text:
                    return text
        except OSError:
            continue
    return ""


def require_service_token(x_ingest_token: str | None = Header(default=None, alias=_HEADER)) -> str:
    expected = service_token()
    if not expected:
        raise HTTPException(status_code=503, detail="service token not configured")
    got = (x_ingest_token or "").strip()
    if got != expected:
        raise HTTPException(status_code=401, detail="unauthorized")
    return expected

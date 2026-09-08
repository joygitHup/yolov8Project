"""Canonical camera stream health from Redis (written by runtime).

API list/dashboard/monitor only read a batched Redis hash. They do not probe
MediaMTX, load detection frames, or evaluate strategies per camera.
"""
from __future__ import annotations


def camera_health(camera, *, streams: dict | None = None, probe_hls: bool = False) -> dict:
    del probe_hls
    rtsp = (getattr(camera, "rtsp", None) or "").strip()
    enabled = bool(getattr(camera, "enabled", False))
    rtsp_configured = bool(rtsp)
    cid = int(camera.id)

    from apps.streaming import mediamtx as mtx
    from apps.common import rdb

    if streams is None:
        shared = rdb.get_stream_health(cid) or {}
    else:
        shared = streams.get(cid) or {}

    path = shared.get("mtxPath") or ""
    if not path and rtsp_configured:
        path = mtx.path_from_rtsp(rtsp, cid)
    hls_url = shared.get("hlsUrl") or (mtx.mtx_hls_url(path) if path else "")
    hls_ready = bool(shared.get("hlsReady"))
    stream_status = shared.get("streamStatus") or ("running" if hls_ready else "idle")
    preview_eligible = bool(enabled and rtsp_configured)

    return {
        "rtspConfigured": rtsp_configured,
        "previewEligible": preview_eligible,
        "hlsUrl": hls_url or None,
        "hlsReady": hls_ready,
        "lastFrameAt": shared.get("lastFrameAt"),
        "hasLastFrame": bool(shared.get("hasLastFrame") or shared.get("lastFrameAt")),
        "inferActive": bool(shared.get("inferActive")),
        "armed": bool(shared.get("armed")),
        "live": bool(hls_ready),
        "streamStatus": stream_status,
        "streamMode": shared.get("streamMode") or ("mediamtx" if path else None),
        "playlistReady": hls_ready,
        "previewReady": hls_ready,
        "mtxPath": path or None,
        "streamError": shared.get("error") or "",
    }

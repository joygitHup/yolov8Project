"""Face analysis sub-module — attaches faceId + faceClear to person detections.

Two paths:

1. **Default (zero heavy deps)** — OpenCV Haar cascade for face detection.
   Computes faceClear quality heuristic (size ratio + blur). Emits faceClear
   boolean but faceId stays empty (no feature library → no person identity).

2. **Upgrade path** — if insightface is importable AND a face feature library
   exists (face_features.npz + user_metadata.json under YOLO_FACE_LIB_PATH),
   uses FaceAnalysis for full detect → 512-dim embedding → Top-1 match.
   Emits real faceId from the library's person_id.

Design follows the "detect-then-recognize" contract from the systemcfg
whitelist rules: faceClear=False means "person box exists but face is
unusable" and faceClear=None means "we didn't even try face analysis on this
box" (non-person classes like car/bus — downstream skips the rule scan).
"""
from __future__ import annotations

import logging
import os
import threading
import uuid
from typing import Any

import numpy as np

logger = logging.getLogger("yolo.face")

# ---------------------------------------------------------------------------
# Global singletons (lazily loaded, thread-safe)
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_insightface_app = None          # insightface.app.FaceAnalysis (or None)
_insightface_err: str | None = None
_face_features: np.ndarray | None = None   # shape (N, 512), L2-normalized
_face_meta: list[dict] = []                # [{faceId, name, path}]
_lib_loaded = False
_lib_err: str | None = None
# Haar cascade path — ships with opencv-python-headless at cv2.data.haarcascades
_haar_cascade = None
_haar_done = False
# Per-track face result cache — trackId → {faceClear, faceId, frame}.
# Face analysis costs ~0.5s/ROI on CPU; with tracking enabled the same person
# keeps the same trackId, so reuse the result for N frames before re-analysis.
_track_cache: dict[str, dict[str, Any]] = {}
_cache_lock = threading.Lock()
_frame_counter = 0
_recheck_frames = max(1, int(os.environ.get("YOLO_FACE_RECHECK_FRAMES") or "30"))
_cache_max = 500
# cosine similarity above which a face is considered a library match
_match_threshold = float(os.environ.get("YOLO_FACE_MATCH_THRESHOLD") or "0.5")


def _haar() -> Any | None:
    global _haar_cascade, _haar_done
    import cv2
    with _lock:
        if _haar_done:
            return _haar_cascade
        _haar_done = True
        try:
            cascade_cls = getattr(cv2, "CascadeClassifier", None)
            if cascade_cls is None:
                # OpenCV 5 builds may drop the legacy objdetect cascade API
                logger.warning("face: cv2 %s has no CascadeClassifier; haar fallback disabled", cv2.__version__)
                return None
            cascade_file = os.path.join(
                cv2.data.haarcascades, "haarcascade_frontalface_default.xml"
            )
            if not os.path.isfile(cascade_file):
                logger.warning("haar cascade not found at %s", cascade_file)
                return None
            _haar_cascade = cascade_cls(cascade_file)
            logger.info("face: haar cascade loaded")
            return _haar_cascade
        except Exception as exc:
            logger.warning("haar cascade load failed: %s", exc)
            return None


def _face_model_name() -> str:
    """insightface model pack name. Env override wins; otherwise auto-detect
    the first available pack under <root>/models (buffalo_sc preferred)."""
    env = (os.environ.get("YOLO_FACE_MODEL") or "").strip()
    if env:
        return env
    models_dir = os.path.join(_face_model_root(), "models")
    for name in ("buffalo_sc", "buffalo_l"):
        if os.path.isdir(os.path.join(models_dir, name)):
            return name
    return "buffalo_sc"


def _face_model_root() -> str:
    return os.path.expanduser(os.environ.get("YOLO_FACE_MODEL_ROOT") or "~/.insightface")


def _try_insightface() -> Any | None:
    """Try to instantiate insightface.FaceAnalysis once. Returns None on any
    failure (missing pkg, missing weights, GPU absent, etc.).

    Weights must already exist on disk — we never let insightface trigger its
    own download here, otherwise the first RTSP frame could block for minutes.
    """
    global _insightface_app, _insightface_err
    with _lock:
        if _insightface_app is not None or _insightface_err is not None:
            return _insightface_app
        try:
            from insightface.app import FaceAnalysis  # type: ignore
        except ImportError:
            _insightface_err = "insightface not installed"
            logger.info("face: insightface not available (pip install insightface)")
            return None
        name = _face_model_name()
        root = _face_model_root()
        model_dir = os.path.join(root, "models", name)
        if not os.path.isdir(model_dir):
            _insightface_err = f"model weights missing: {model_dir}"
            logger.info(
                "face: insightface model %s not found at %s (falling back to haar)",
                name, model_dir,
            )
            return None
        try:
            # detection + recognition only — skip landmark/genderage models
            # (buffalo_l full pack costs ~2s/face on CPU otherwise)
            app = FaceAnalysis(
                name=name,
                root=root,
                providers=["CPUExecutionProvider"],
                allowed_modules=["detection", "recognition"],
            )
            app.prepare(ctx_id=0, det_size=(640, 640))
            _insightface_app = app
            logger.info("face: insightface FaceAnalysis ready (%s)", name)
            return app
        except Exception as exc:
            _insightface_err = str(exc)
            logger.warning("face: insightface init failed: %s (falling back to haar)", exc)
            return None


def _face_lib_path() -> str:
    """Directory containing face_features.npz + user_metadata.json."""
    p = os.environ.get("YOLO_FACE_LIB_PATH") or ""
    if p and os.path.isdir(p):
        return p
    default = os.path.join(os.path.dirname(__file__), "..", "face_lib")
    if os.path.isdir(default):
        return default
    return ""


def _load_face_library() -> None:
    """Load face feature bank once — called lazily on first frame."""
    global _face_features, _face_meta, _lib_loaded, _lib_err
    with _lock:
        if _lib_loaded or _lib_err is not None:
            return
        _lib_loaded = True  # mark to prevent retry storm; reset on failure below
        lib_dir = _face_lib_path()
        if not lib_dir:
            logger.info("face: no face library directory set (YOLO_FACE_LIB_PATH)")
            return
        npz = os.path.join(lib_dir, "face_features.npz")
        meta = os.path.join(lib_dir, "user_metadata.json")
        if not os.path.isfile(npz):
            logger.info("face: feature bank not found at %s", npz)
            return
        try:
            data = np.load(npz, allow_pickle=True)
            keys: list[str] = []
            # npz may have 'features'/'ids' arrays OR be {face_id: vector}
            if "features" in data.files and "ids" in data.files:
                feats = np.asarray(data["features"], dtype=np.float32)
                if feats.ndim == 1:
                    feats = feats.reshape(1, -1)
                keys = [str(k) for k in np.asarray(data["ids"]).reshape(-1).tolist()]
            else:
                values = [np.asarray(data[k], dtype=np.float32).reshape(-1)
                          for k in data.files if np.asarray(data[k]).ndim == 1]
                keys = [k for k in data.files if np.asarray(data[k]).ndim == 1]
                feats = np.stack(values, axis=0) if values else np.zeros((0, 512), dtype=np.float32)
            if feats.size == 0 or feats.shape[0] == 0:
                logger.warning("face: npz has no embeddings")
                return
            # L2-normalize for cosine similarity
            norms = np.linalg.norm(feats, axis=1, keepdims=True) + 1e-8
            _face_features = feats / norms
            logger.info("face: loaded %d embeddings shape=%s from %s",
                        len(keys), feats.shape, npz)
        except Exception as exc:
            _lib_err = str(exc)
            logger.exception("face: failed to load npz: %s", exc)
            return
        # metadata
        try:
            import json
            with open(meta, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            if isinstance(raw, dict):
                _face_meta = [
                    {"faceId": str(k), "name": v.get("name", k) if isinstance(v, dict) else k}
                    for k, v in raw.items()
                ]
            elif isinstance(raw, list):
                _face_meta = [
                    {"faceId": str(item.get("faceId") or item.get("id", "")),
                     "name": item.get("name", "")}
                    for item in raw if isinstance(item, dict)
                ]
        except Exception as exc:
            logger.warning("face: metadata load skipped: %s", exc)
        # align keys with features
        if len(keys) != len(_face_meta):
            _face_meta = [{"faceId": k, "name": ""} for k in keys]


# ---------------------------------------------------------------------------
# Quality heuristic — used to decide faceClear
# ---------------------------------------------------------------------------

def _blur_score(face_bgr: np.ndarray) -> float:
    """Laplacian variance — low = blurry. Range typically <50 blurry, >200 sharp."""
    import cv2
    if face_bgr is None or face_bgr.size == 0:
        return 0.0
    gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY) if face_bgr.ndim == 3 else face_bgr
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _clear_from_heuristics(face_score: float, face_ratio: float, blur: float) -> bool:
    """
    face_score : insightface det score OR haar neighbours_accepted (int)
    face_ratio : face bbox area / person bbox area
    blur       : Laplacian variance

    Loose thresholds — err on the side of True (treat as clear).
    Only mark False when two independent signals are bad.
    """
    # Bad cases — face too small or blurry
    face_too_small = face_ratio < 0.02
    face_too_blurry = blur < 20.0
    # detection confidence thresholds
    low_det_score = face_score < 0.3 if face_score <= 1.0 else face_score < 3  # haar neighbours

    # Clear = at most ONE of these three fails
    bad = sum([face_too_small, face_too_blurry, low_det_score])
    return bad <= 1


# ---------------------------------------------------------------------------
# Face attach entry point
# ---------------------------------------------------------------------------

# Person label synonyms (YOLO COCO has "person"; custom models may use zh names)
_PERSON_LABELS = {"person", "人", "人员", "路人", "员工", "employee", "pedestrian"}


def attach(frame_bgr: np.ndarray, detections: list[dict[str, Any]]) -> None:
    """Mutate each detection dict with faceId / faceClear fields in-place.

    Non-person boxes get faceClear=None and faceId="" (meaning "face analysis
    not attempted" — downstream whitelist skips face rules for those).
    Person boxes get real face analysis results.
    """
    if frame_bgr is None or not detections:
        return
    h, w = frame_bgr.shape[:2]
    if h <= 0 or w <= 0:
        return

    insightface = _try_insightface()
    if insightface is not None:
        _load_face_library()

    import cv2  # local import — cv2 module-level imported elsewhere too

    global _frame_counter
    with _cache_lock:
        _frame_counter += 1
        frame_no = _frame_counter

    for det in detections:
        label = str(det.get("label") or "").strip().lower()
        bbox = det.get("bbox") or {}
        bx = float(bbox.get("x", 0.0))
        by = float(bbox.get("y", 0.0))
        bw = float(bbox.get("w", 0.0))
        bh = float(bbox.get("h", 0.0))

        # Non-person — mark as "not attempted"
        if label not in _PERSON_LABELS:
            det["faceClear"] = None
            det["faceId"] = ""
            continue

        # Reuse cached result for recently-seen tracks — recognition is the
        # expensive part and tracking already ties the same person together.
        track_id = str(det.get("trackId") or "").strip()
        if track_id:
            with _cache_lock:
                cached = _track_cache.get(track_id)
            if cached and frame_no - cached["frame"] < _recheck_frames:
                det["faceClear"] = cached["faceClear"]
                det["faceId"] = cached["faceId"]
                continue

        # Absolute pixel coordinates
        abs_x1 = int(bx * w)
        abs_y1 = int(by * h)
        abs_x2 = int((bx + bw) * w)
        abs_y2 = int((by + bh) * h)
        abs_x1 = max(0, abs_x1); abs_y1 = max(0, abs_y1)
        abs_x2 = min(w, abs_x2); abs_y2 = min(h, abs_y2)
        pw, ph = abs_x2 - abs_x1, abs_y2 - abs_y1
        if pw < 10 or ph < 10:
            det["faceClear"] = None
            det["faceId"] = ""
            continue

        person_roi = frame_bgr[abs_y1:abs_y2, abs_x1:abs_x2]
        face_id = ""
        face_clear = False

        if insightface is not None:
            # --- insightface path ---
            try:
                faces = insightface.get(person_roi)
            except Exception as exc:
                logger.debug("insightface.get failed: %s", exc)
                faces = []
            if faces:
                face = faces[0]
                # face.bbox is absolute coords inside the person ROI
                fx1, fy1, fx2, fy2 = [int(v) for v in face.bbox]
                fa = max(0, fx2 - fx1) * max(0, fy2 - fy1)
                pa = pw * ph + 1e-6
                face_ratio = fa / pa
                face_roi = person_roi[fy1:fy2, fx1:fx2]
                blur = _blur_score(face_roi)
                face_clear = _clear_from_heuristics(face.det_score, face_ratio, blur)

                # recognition — cosine against _face_features
                emb = face.embedding
                if emb is not None and _face_features is not None and face_clear:
                    emb = np.asarray(emb, dtype=np.float32).reshape(1, -1)
                    emb = emb / (np.linalg.norm(emb) + 1e-8)
                    sims = (_face_features @ emb.T).flatten()  # cosine
                    top_idx = int(np.argmax(sims))
                    top_sim = float(sims[top_idx])
                    if top_sim >= _match_threshold:
                        face_id = _face_meta[top_idx]["faceId"] if top_idx < len(_face_meta) else ""
            else:
                face_clear = False  # person box but no face detected
        else:
            # --- Haar fallback ---
            cascade = _haar()
            if cascade is not None:
                gray = cv2.cvtColor(person_roi, cv2.COLOR_BGR2GRAY)
                # scaleFactor, minNeighbors, minSize
                haar_faces = cascade.detectMultiScale(
                    gray, scaleFactor=1.1, minNeighbors=4, minSize=(20, 20)
                )
                if len(haar_faces) > 0:
                    fx, fy, fw_, fh_ = haar_faces[0]
                    fa = fw_ * fh_
                    pa = pw * ph + 1e-6
                    face_ratio = fa / pa
                    face_roi = person_roi[fy:fy + fh_, fx:fx + fw_]
                    blur = _blur_score(face_roi)
                    face_clear = _clear_from_heuristics(0.5, face_ratio, blur)
                    # no feature library — faceId stays empty
                else:
                    face_clear = False
            else:
                # No haar either — can't attempt face analysis
                det["faceClear"] = None
                det["faceId"] = ""
                continue

        det["faceClear"] = bool(face_clear)
        det["faceId"] = str(face_id) if face_id else ""

        if track_id:
            with _cache_lock:
                if len(_track_cache) >= _cache_max and track_id not in _track_cache:
                    oldest = min(_track_cache, key=lambda k: _track_cache[k]["frame"])
                    _track_cache.pop(oldest, None)
                _track_cache[track_id] = {
                    "faceClear": det["faceClear"],
                    "faceId": det["faceId"],
                    "frame": frame_no,
                }


# ---------------------------------------------------------------------------
# Health / status helpers exposed to main.py / GET /health
# ---------------------------------------------------------------------------

def face_status() -> dict[str, Any]:
    return {
        "enabled": True,
        "model": _face_model_name(),
        "modelDir": os.path.join(_face_model_root(), "models", _face_model_name()),
        "modelPresent": os.path.isdir(
            os.path.join(_face_model_root(), "models", _face_model_name())
        ),
        "insightface": _insightface_app is not None,
        "insightfaceErr": _insightface_err,
        "library": _face_lib_path(),
        "libraryLoaded": _lib_loaded and _face_features is not None,
        "libraryErr": _lib_err,
        "haar": _haar_cascade is not None,
        "personLabels": sorted(_PERSON_LABELS),
    }


def prewarm() -> None:
    """Warm up insightface + feature library in a background thread so the
    first person frame doesn't pay the multi-second model-load cost, and so
    /health reflects the real face stack state immediately."""
    def _run():
        app = _try_insightface()
        if app is not None:
            _load_face_library()
            logger.info("face: prewarm complete")
    threading.Thread(target=_run, name="face-prewarm", daemon=True).start()


# ---------------------------------------------------------------------------
# Library management (enroll / delete / list via API)
# ---------------------------------------------------------------------------

def _invalidate_library() -> None:
    """Force reload of the feature bank on next attach() call."""
    global _face_features, _face_meta, _lib_loaded, _lib_err
    with _lock:
        _face_features = None
        _face_meta = []
        _lib_loaded = False
        _lib_err = None


def _lib_dir_or_create() -> str:
    lib = _face_lib_path()
    if lib:
        return lib
    lib = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "face_lib"))
    os.makedirs(lib, exist_ok=True)
    return lib


def _npz_file() -> str:
    return os.path.join(_lib_dir_or_create(), "face_features.npz")


def _meta_file() -> str:
    return os.path.join(_lib_dir_or_create(), "user_metadata.json")


def _read_metadata() -> dict[str, dict[str, Any]]:
    import json
    try:
        with open(_meta_file(), "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except Exception:
        return {}
    if isinstance(raw, dict):
        return {str(k): v for k, v in raw.items() if isinstance(v, dict)}
    if isinstance(raw, list):
        return {str(i.get("faceId")): i for i in raw if isinstance(i, dict) and i.get("faceId")}
    return {}


def _write_metadata(meta: dict[str, dict[str, Any]]) -> None:
    import json
    tmp = _meta_file() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, _meta_file())


def _read_npz() -> tuple[list[str], np.ndarray]:
    """(ids, features). Empty library → ([], zeros((0,512)))."""
    npz = _npz_file()
    if not os.path.isfile(npz):
        return [], np.zeros((0, 512), dtype=np.float32)
    data = np.load(npz, allow_pickle=True)
    if "features" in data.files and "ids" in data.files:
        feats = np.asarray(data["features"], dtype=np.float32)
        ids = [str(k) for k in np.asarray(data["ids"]).reshape(-1).tolist()]
        if feats.ndim == 1:
            feats = feats.reshape(1, -1)
        return ids, feats
    ids = [k for k in data.files if np.asarray(data[k]).ndim == 1]
    feats = (np.stack([np.asarray(data[k], dtype=np.float32).reshape(-1) for k in ids], axis=0)
             if ids else np.zeros((0, 512), dtype=np.float32))
    return ids, feats


def _write_npz(ids: list[str], feats: np.ndarray) -> None:
    # Atomic write — camera threads may be reading the file concurrently.
    tmp = _npz_file() + ".tmp"
    with open(tmp, "wb") as fh:
        np.savez(fh, ids=np.asarray(ids), features=feats.astype(np.float32))
    os.replace(tmp, _npz_file())


def face_photo_path(face_id: str) -> str:
    lib = _face_lib_path()
    if not lib:
        return ""
    p = os.path.join(lib, "photos", f"{face_id}.jpg")
    return p if os.path.isfile(p) else ""


def list_faces() -> list[dict[str, Any]]:
    meta = _read_metadata()
    ids, _ = _read_npz()
    return [
        {
            "faceId": fid,
            "name": str((meta.get(fid) or {}).get("name") or ""),
            "createdAt": str((meta.get(fid) or {}).get("createdAt") or ""),
            "source": str((meta.get(fid) or {}).get("source") or ""),
            "hasPhoto": bool(face_photo_path(fid)),
        }
        for fid in ids
    ]


def enroll_face(name: str, image_bytes: bytes) -> dict[str, Any]:
    """Extract the largest face's embedding from an uploaded photo and append
    it to the feature bank. Raises ValueError for bad input, RuntimeError when
    the recognition stack is unavailable."""
    import cv2
    from datetime import datetime, timezone

    name = (name or "").strip()
    if not name:
        raise ValueError("姓名不能为空")
    if len(image_bytes) > 10 * 1024 * 1024:
        raise ValueError("图片过大（>10MB）")
    _lib_dir_or_create()
    app = _try_insightface()
    if app is None:
        raise RuntimeError(f"insightface 不可用：{_insightface_err or 'unknown'}")
    img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("图片解码失败，请使用 JPG/PNG")
    faces = app.get(img)
    if not faces:
        raise ValueError("未检测到人脸，请使用清晰的正脸照片")
    face = max(faces, key=lambda f: max(0.0, f.bbox[2] - f.bbox[0]) * max(0.0, f.bbox[3] - f.bbox[1]))
    emb = np.asarray(face.embedding, dtype=np.float32).reshape(-1)
    emb = emb / (np.linalg.norm(emb) + 1e-8)

    face_id = f"fae-{uuid.uuid4().hex[:10]}"
    ids, feats = _read_npz()
    ids.append(face_id)
    feats = np.vstack([feats, emb.reshape(1, -1)]) if feats.size else emb.reshape(1, -1)
    _write_npz(ids, feats)

    meta = _read_metadata()
    meta[face_id] = {
        "faceId": face_id,
        "name": name,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "source": "upload",
    }
    _write_metadata(meta)

    photos = os.path.join(_lib_dir_or_create(), "photos")
    os.makedirs(photos, exist_ok=True)
    ok, buf = cv2.imencode(".jpg", img)
    if ok:
        photo = os.path.join(photos, f"{face_id}.jpg")
        tmp = photo + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(buf.tobytes())
        os.replace(tmp, photo)

    _invalidate_library()
    logger.info("face: enrolled %s (%s), library now %d identities", face_id, name, len(ids))
    return {"faceId": face_id, "name": name, "detScore": round(float(face.det_score), 4), "total": len(ids)}


def delete_face(face_id: str) -> bool:
    face_id = (face_id or "").strip()
    if not face_id:
        return False
    ids, feats = _read_npz()
    if face_id not in ids:
        return False
    idx = ids.index(face_id)
    ids.pop(idx)
    feats = np.delete(feats, idx, axis=0)
    if ids:
        _write_npz(ids, feats)
    else:
        try:
            os.remove(_npz_file())
        except OSError:
            pass
    meta = _read_metadata()
    meta.pop(face_id, None)
    _write_metadata(meta)
    photo = face_photo_path(face_id)
    if photo:
        try:
            os.remove(photo)
        except OSError:
            pass
    _invalidate_library()
    logger.info("face: deleted %s, library now %d identities", face_id, len(ids))
    return True

"""Generate face_features.npz + user_metadata.json face library.

Two modes:

1) SINGLE_IMAGE — point at a single person photo (jpg/png):
       python yolo-service/scripts/make_face_lib.py --add "张三" "C:/photos/zhangsan.jpg"

2) DEMO — create a tiny demo library with synthetic embeddings for testing:
       python yolo-service/scripts/make_face_lib.py --demo

Face library lives at yolo-service/face_lib/ (or $YOLO_FACE_LIB_PATH).
yolo-service reads it on startup and does cosine-similarity matching.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

LIB_DIR = Path(os.environ.get("YOLO_FACE_LIB_PATH") or
               (Path(__file__).resolve().parent.parent / "face_lib"))
NPZ = LIB_DIR / "face_features.npz"
META = LIB_DIR / "user_metadata.json"


def _load_insightface():
    from insightface.app import FaceAnalysis
    app = FaceAnalysis(name="buffalo_sc",
                       root=str(Path.home() / ".insightface"),
                       providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=0, det_size=(640, 640))
    return app


def _load_existing() -> tuple[dict[str, np.ndarray], dict[str, dict]]:
    feats: dict[str, np.ndarray] = {}
    meta: dict[str, dict] = {}
    if NPZ.exists():
        data = np.load(NPZ, allow_pickle=True)
        if "ids" in data.files and "features" in data.files:
            ids = data["ids"].tolist()
            arr = data["features"]
            feats = {str(ids[i]): arr[i].astype(np.float32) for i in range(len(ids))}
    if META.exists():
        try:
            meta = json.loads(META.read_text(encoding="utf-8"))
            if isinstance(meta, list):
                meta = {str(item.get("faceId") or item.get("id", "")): item
                        for item in meta if isinstance(item, dict)}
        except Exception:
            meta = {}
    return feats, meta


def _save(feats: dict[str, np.ndarray], meta: dict[str, dict]) -> None:
    LIB_DIR.mkdir(parents=True, exist_ok=True)
    ids = list(feats.keys())
    arr = np.stack([feats[k] for k in ids], axis=0).astype(np.float32)
    np.savez(NPZ, ids=np.array(ids), features=arr)
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {len(ids)} identities:")
    for fid, info in meta.items():
        print(f"  faceId={fid}  name={info.get('name', '')}")
    print(f"  → {NPZ}")
    print(f"  → {META}")


def add_person(name: str, image_path: str) -> None:
    import cv2
    app = _load_insightface()
    img = cv2.imread(image_path)
    if img is None:
        print(f"ERROR: can't read {image_path}")
        sys.exit(1)
    faces = app.get(img)
    if not faces:
        print(f"ERROR: no face detected in {image_path}")
        sys.exit(1)
    # Largest face
    face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
    emb = face.embedding
    if emb is None:
        print("ERROR: face has no embedding")
        sys.exit(1)

    # Normalize
    emb = emb.astype(np.float32).reshape(-1)
    emb = emb / (np.linalg.norm(emb) + 1e-8)

    fid = f"fae-{name}-{np.random.randint(100000, 999999)}"
    feats, meta = _load_existing()
    feats[fid] = emb
    meta[fid] = {"faceId": fid, "name": name, "source": image_path, "createdAt": __import__("datetime").datetime.utcnow().isoformat()}
    _save(feats, meta)


def make_demo() -> None:
    """Create a 3-person demo library with synthetic embeddings.

    These won't match real faces but let you verify the whitelist faceIds
    end-to-end (rule-based suppression + review path).
    """
    rng = np.random.default_rng(42)
    feats: dict[str, np.ndarray] = {}
    meta: dict[str, dict] = {}
    names = ["张三 (值班员)", "李四 (访客)", "王五 (黑名单)"]
    for idx, name in enumerate(names, start=1):
        emb = rng.normal(size=512).astype(np.float32)
        emb = emb / (np.linalg.norm(emb) + 1e-8)
        fid = f"fae-demo-{idx}"
        feats[fid] = emb
        meta[fid] = {"faceId": fid, "name": name, "source": "demo", "createdAt": "demo"}
    _save(feats, meta)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--add", nargs=2, metavar=("NAME", "IMAGE_PATH"),
                    help="Add one person: name + photo path")
    ap.add_argument("--demo", action="store_true",
                    help="Create 3 synthetic demo identities (no insightface needed)")
    ap.add_argument("--clear", action="store_true",
                    help="Wipe existing face library before adding/demo")
    args = ap.parse_args()

    if args.clear:
        feats, meta = {}, {}
        if NPZ.exists(): NPZ.unlink()
        if META.exists(): META.unlink()
        print("Cleared existing library.")

    if args.demo:
        make_demo()
    elif args.add:
        name, path = args.add
        add_person(name, path)
    else:
        ap.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

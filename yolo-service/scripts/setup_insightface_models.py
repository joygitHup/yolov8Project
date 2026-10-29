"""Extract buffalo_sc weights, verify FaceAnalysis, and point to the demo library.

Usage:
    python yolo-service/scripts/setup_insightface_models.py                 # use ~/.insightface/buffalo_sc.zip
    python yolo-service/scripts/setup_insightface_models.py D:/dl/buffalo_sc.zip
    python yolo-service/scripts/setup_insightface_models.py --skip-verify    # if weights are already in place
"""
from __future__ import annotations

import os
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path.home() / ".insightface"
ZIP_PATH = ROOT / "buffalo_sc.zip"
MODEL_DIR = ROOT / "models" / "buffalo_sc"


def model_ready() -> bool:
    return MODEL_DIR.is_dir() and any(MODEL_DIR.glob("*.onnx"))


def wait_for_zip(timeout_sec: int = 1800) -> bool:
    t0 = time.time()
    last_size = -1
    stall = 0
    while time.time() - t0 < timeout_sec:
        if ZIP_PATH.exists():
            size = ZIP_PATH.stat().st_size
            if size > 0:
                if size == last_size:
                    stall += 1
                else:
                    stall = 0
                last_size = size
                print(f"  {size/1024/1024:.1f}MB downloaded...", end="\r", flush=True)
        if stall > 60:
            print("\nDownload stalled for 60s — retrying may be needed.")
            return False
        time.sleep(3)
    print("\nDownload timeout.")
    return False


def extract(zip_path: Path = ZIP_PATH) -> bool:
    if not zip_path.exists() or zip_path.stat().st_size < 1_000_000:
        print(f"zip missing or too small: {zip_path}")
        return False
    print(f"Extracting {zip_path} → {MODEL_DIR}")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(MODEL_DIR)
        onnx_files = list(MODEL_DIR.glob("*.onnx"))
        print(f"  onnx files: {[f.name for f in onnx_files]}")
        if not onnx_files:
            # Maybe files are in a subfolder
            for sub in MODEL_DIR.iterdir():
                if sub.is_dir():
                    onnx_files = list(sub.glob("*.onnx"))
                    if onnx_files:
                        print(f"  found in subdir {sub.name}: {[f.name for f in onnx_files]}")
                        # Move up
                        for f in onnx_files:
                            f.rename(MODEL_DIR / f.name)
            onnx_files = list(MODEL_DIR.glob("*.onnx"))
        return len(onnx_files) > 0
    except Exception as exc:
        print(f"extract failed: {exc}")
        return False


def verify() -> bool:
    print("\nVerifying FaceAnalysis init + detect + embedding...")
    import numpy as np
    from insightface.app import FaceAnalysis

    try:
        app = FaceAnalysis(name="buffalo_sc", root=str(Path.home() / ".insightface"),
                           providers=["CPUExecutionProvider"])
        app.prepare(ctx_id=0, det_size=(640, 640))
        print("  FaceAnalysis ready")

        # Test on generated frame with face oval
        import cv2
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.ellipse(frame, (320, 240), (80, 110), 0, 0, 360, (200, 180, 160), -1)
        t0 = time.time()
        faces = app.get(frame)
        dt = (time.time() - t0) * 1000
        print(f"  detect {len(faces)} face(s) in {dt:.0f}ms")
        for i, f in enumerate(faces[:3]):
            emb_shape = f.embedding.shape if f.embedding is not None else None
            print(f"    face[{i}] score={f.det_score:.3f} emb={emb_shape}")
        return True
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return False


def main():
    os.environ.setdefault("YOLO_INFER_MODE", "local")
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    skip_verify = "--skip-verify" in sys.argv[1:]
    zip_path = Path(args[0]).expanduser() if args else ZIP_PATH

    print("=== insightface buffalo_sc setup ===")
    print(f"zip: {zip_path}")
    print(f"model_dir: {MODEL_DIR}")

    if model_ready():
        print("model weights already present — skip extract")
    else:
        if not zip_path.exists() or zip_path.stat().st_size < 1_000_000:
            if zip_path != ZIP_PATH:
                print(f"\nbuffalo_sc.zip not found at {zip_path}")
                return 1
            print("\nbuffalo_sc.zip not found. Starting wait loop (Ctrl+C to cancel)...")
            if not wait_for_zip():
                return 1
        if not extract(zip_path):
            return 2

    if not skip_verify and not verify():
        return 3

    print("\n=== ALL GOOD. Now generate a face library: ===")
    print("  python yolo-service/scripts/make_face_lib.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())

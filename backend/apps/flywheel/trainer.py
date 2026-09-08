"""Fine-tune current weights on original dataset + reviewed field samples.

Training runs in the runtime process (`manage.py run_runtime` / flywheel.train job),
never inside the Django HTTP loop.
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

from django.db import close_old_connections
from django.utils import timezone

from apps.common import storage
from apps.flywheel.dataset import boxes_to_yolo_txt, class_id_for_label
from apps.flywheel.models import FlywheelSample, FlywheelTrainRun
from apps.systemcfg.model_names import DEFAULT_MODEL_CLASS_NAMES
from apps.systemcfg.services import get_section, save_section

logger = logging.getLogger("flywheel.train")

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

_lock = threading.Lock()


def run_to_dict(run: FlywheelTrainRun) -> dict:
    return {
        "id": run.id,
        "status": run.status,
        "operator": run.operator,
        "reviewedCount": run.reviewed_count,
        "exported": run.exported,
        "epochs": run.epochs,
        "baseWeights": run.base_weights,
        "newWeights": run.new_weights,
        "previousWeights": run.previous_weights,
        "oldMap50": run.old_map50,
        "newMap50": run.new_map50,
        "promoted": run.promoted,
        "message": run.message,
        "log": (run.log or "")[-4000:],
        "startedAt": run.started_at.isoformat() if run.started_at else None,
        "finishedAt": run.finished_at.isoformat() if run.finished_at else None,
    }


def latest_run() -> FlywheelTrainRun | None:
    return FlywheelTrainRun.objects.order_by("-id").first()


def start_train(*, operator: str = "") -> FlywheelTrainRun:
    cfg = get_section("flywheel")
    min_n = int(cfg.get("minReviewed") or 5)
    approved = FlywheelSample.objects.filter(status="approved")
    n = approved.count()
    if n < min_n:
        raise ValueError(f"已通过样本不足（{n}/{min_n}），请先在标注台审核")
    if FlywheelTrainRun.objects.filter(status__in=("queued", "running")).exists():
        raise ValueError("已有训练任务在进行")
    det = get_section("detection")
    base = str(det.get("modelPath") or "").strip()
    if not base or not Path(base).is_file():
        raise ValueError("当前模型权重不存在，请先在检测参数里填写有效的 modelPath")
    root = Path(str(cfg.get("trainRoot") or "")).expanduser()
    if not root.is_dir():
        raise ValueError(f"训练目录不存在：{root}")
    run = FlywheelTrainRun.objects.create(
        status="queued",
        operator=(operator or "")[:64],
        reviewed_count=n,
        epochs=int(cfg.get("epochs") or 15),
        base_weights=base,
        previous_weights=base,
        message="已排队，等待 runtime 消费…",
    )
    from apps.common.jobs import QUEUE_FLYWHEEL, enqueue

    try:
        enqueue(QUEUE_FLYWHEEL, "flywheel.train", {"runId": run.id})
    except Exception as exc:
        run.status = "failed"
        run.message = f"入队失败：{exc}"[:512]
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "message", "finished_at"])
        raise
    return run


def promote_run(run: FlywheelTrainRun, *, operator: str = "") -> FlywheelTrainRun:
    if not run.new_weights or not Path(run.new_weights).is_file():
        raise ValueError("没有可上线的新权重")
    _activate_weights(run.new_weights)
    run.status = "promoted"
    run.promoted = True
    run.operator = (operator or run.operator or "")[:64]
    run.message = "已强制上线新权重"
    run.finished_at = timezone.now()
    run.save()
    return run


def rollback_run(run: FlywheelTrainRun) -> FlywheelTrainRun:
    prev = (run.previous_weights or run.base_weights or "").strip()
    if not prev or not Path(prev).is_file():
        raise ValueError("没有可回滚的旧权重")
    _activate_weights(prev)
    run.message = f"已回滚到 {prev}"
    run.save(update_fields=["message"])
    return run


def _append(run: FlywheelTrainRun, line: str) -> None:
    run.log = ((run.log or "") + line + "\n")[-12000:]
    run.message = line[:512]
    run.save(update_fields=["log", "message"])
    logger.info("train #%s %s", run.id, line)


def _list_images(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS)


def _load_base_names(root: Path) -> list[str]:
    yaml_path = root / "dataset" / "data.yaml"
    names: list[str] = []
    if yaml_path.is_file():
        in_names = False
        for raw in yaml_path.read_text(encoding="utf-8").splitlines():
            line = raw.rstrip()
            if line.strip() == "names:" or line.strip().startswith("names:"):
                in_names = True
                if "[" in line and "]" in line:
                    inner = line.split("[", 1)[1].split("]", 1)[0]
                    names = [x.strip().strip("\"'") for x in inner.split(",") if x.strip()]
                    break
                continue
            if in_names:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if not stripped[:1].isdigit() and ":" in stripped and not stripped.startswith("-"):
                    break
                if ":" in stripped:
                    names.append(stripped.split(":", 1)[1].strip().strip("\"'"))
                elif stripped.startswith("-"):
                    names.append(stripped[1:].strip().strip("\"'"))
    return names or list(DEFAULT_MODEL_CLASS_NAMES)


def _class_id(label: str, names: list[str]) -> int | None:
    return class_id_for_label(label, names)


def _export_reviewed(root: Path, names: list[str], run: FlywheelTrainRun) -> list[Path]:
    out_img = root / "dataset" / "flywheel" / "images"
    out_lbl = root / "dataset" / "flywheel" / "labels"
    out_img.mkdir(parents=True, exist_ok=True)
    out_lbl.mkdir(parents=True, exist_ok=True)
    exported: list[Path] = []
    samples = FlywheelSample.objects.filter(status="approved").order_by("id")
    for sample in samples:
        key = sample.reviewed_image_key or sample.image_key
        jpeg = storage.get_bytes(key)
        if not jpeg:
            _append(run, f"跳过无图样本 #{sample.id}")
            continue
        img_path = out_img / f"{sample.stem}.jpg"
        img_path.write_bytes(jpeg)
        boxes = sample.boxes if isinstance(sample.boxes, list) else []
        remapped = []
        for item in boxes:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "")
            cid = _class_id(label, names)
            if cid is None:
                continue
            copy = dict(item)
            copy["label"] = names[cid]
            remapped.append(copy)
        txt, _count = boxes_to_yolo_txt(remapped, names)
        (out_lbl / f"{sample.stem}.txt").write_text(txt or "\n", encoding="utf-8")
        exported.append(img_path)
    run.exported = len(exported)
    run.save(update_fields=["exported"])
    return exported


def _write_mix_lists(root: Path, fw_images: list[Path], names: list[str]) -> Path:
    dataset = root / "dataset"
    orig_train = _list_images(dataset / "images" / "train")
    orig_val = _list_images(dataset / "images" / "val")
    if not orig_train:
        raise RuntimeError(f"原训练集为空：{dataset / 'images' / 'train'}")
    if not orig_val:
        orig_val = orig_train[:]
    # Keep original val for a fair mAP compare; all field samples go to train.
    train_paths = orig_train + fw_images
    val_paths = orig_val
    train_txt = dataset / "flywheel_train.txt"
    val_txt = dataset / "flywheel_val.txt"
    train_txt.write_text("\n".join(p.resolve().as_posix() for p in train_paths) + "\n", encoding="utf-8")
    val_txt.write_text("\n".join(p.resolve().as_posix() for p in val_paths) + "\n", encoding="utf-8")
    yaml_path = dataset / "flywheel.yaml"
    lines = [
        f"path: {dataset.resolve().as_posix()}",
        "train: flywheel_train.txt",
        "val: flywheel_val.txt",
        "names:",
    ]
    for i, name in enumerate(names):
        lines.append(f"  {i}: {name}")
    yaml_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return yaml_path


def _map50(metrics) -> float | None:
    try:
        val = getattr(getattr(metrics, "box", metrics), "map50", None)
        if val is None:
            val = getattr(metrics, "map50", None)
        return None if val is None else round(float(val), 4)
    except Exception:
        return None


def _activate_weights(path: str) -> None:
    detection = get_section("detection")
    detection["modelPath"] = path
    save_section("detection", detection)
    try:
        from apps.inference import remote as yolo_remote

        if yolo_remote.infer_mode() == "remote":
            yolo_remote.reload_model(path)
    except Exception:
        logger.exception("reload yolo-service failed path=%s", path)


def run_train_job(run_id: int) -> None:
    _train_thread(run_id)


def _train_thread(run_id: int) -> None:
    if not _lock.acquire(blocking=False):
        close_old_connections()
        FlywheelTrainRun.objects.filter(pk=run_id).update(status="failed", message="训练锁占用")
        return
    close_old_connections()
    run = FlywheelTrainRun.objects.filter(pk=run_id).first()
    if not run:
        _lock.release()
        return
    try:
        cfg = get_section("flywheel")
        if run.status in ("queued", "running"):
            run.status = "running"
            run.message = "开始训练"
            run.save(update_fields=["status", "message"])
        root = Path(str(cfg.get("trainRoot") or "")).expanduser()
        names = _load_base_names(root)
        _append(run, f"导出已通过样本，类别数={len(names)}")
        fw_images = _export_reviewed(root, names, run)
        if not fw_images:
            raise RuntimeError("没有成功导出任何已通过样本")
        yaml_path = _write_mix_lists(root, fw_images, names)
        _append(run, f"混合数据集已写入 {yaml_path}（原数据 + {len(fw_images)} 张现场图）")

        from ultralytics import YOLO

        device = str(cfg.get("trainDevice") or os.environ.get("YOLO_DEVICE") or "cpu")
        epochs = int(cfg.get("epochs") or 15)
        batch = int(cfg.get("batch") or 4)
        imgsz = int(cfg.get("imgsz") or 640)
        project = root / "runs" / "detect"
        name = f"flywheel_{run.id}"
        _append(run, f"开始微调 epochs={epochs} batch={batch} device={device}")
        model = YOLO(run.base_weights)
        results = model.train(
            data=str(yaml_path),
            epochs=epochs,
            imgsz=imgsz,
            batch=batch,
            device=device,
            workers=0,
            project=str(project),
            name=name,
            exist_ok=True,
            patience=max(5, epochs // 3),
            plots=False,
            verbose=True,
            pretrained=True,
        )
        save_dir = Path(str(getattr(results, "save_dir", project / name)))
        best = save_dir / "weights" / "best.pt"
        if not best.is_file():
            last = save_dir / "weights" / "last.pt"
            if last.is_file():
                best = last
        if not best.is_file():
            raise RuntimeError("训练结束但未找到 best.pt")
        run.new_weights = str(best)
        run.save(update_fields=["new_weights"])
        _append(run, f"新权重 {best}")

        _append(run, "对比原验证集 mAP50")
        old_m = YOLO(run.base_weights).val(data=str(yaml_path), split="val", workers=0, verbose=False)
        new_m = YOLO(str(best)).val(data=str(yaml_path), split="val", workers=0, verbose=False)
        run.old_map50 = _map50(old_m)
        run.new_map50 = _map50(new_m)
        run.save(update_fields=["old_map50", "new_map50"])
        old_s = "n/a" if run.old_map50 is None else f"{run.old_map50:.3f}"
        new_s = "n/a" if run.new_map50 is None else f"{run.new_map50:.3f}"
        _append(run, f"mAP50 旧={old_s} 新={new_s}")

        max_drop = float(cfg.get("maxMapDrop") or 0.01)
        improved = True
        if run.old_map50 is not None and run.new_map50 is not None:
            improved = run.new_map50 + 1e-9 >= run.old_map50 - max_drop
        if improved:
            _activate_weights(str(best))
            run.status = "promoted"
            run.promoted = True
            run.message = f"已上线新权重 mAP50 {old_s} → {new_s}"
        else:
            run.status = "rejected"
            run.promoted = False
            run.message = f"新模型回退（mAP50 {old_s} → {new_s}，降幅超过 {max_drop}）"
        run.finished_at = timezone.now()
        run.save()
        logger.info("train #%s done status=%s", run.id, run.status)
    except Exception as exc:
        logger.exception("train #%s failed", run_id)
        run.status = "failed"
        run.message = str(exc)[:512]
        run.finished_at = timezone.now()
        run.log = ((run.log or "") + f"ERROR {exc}\n")[-12000:]
        run.save()
    finally:
        try:
            _lock.release()
        except Exception:
            pass
        close_old_connections()

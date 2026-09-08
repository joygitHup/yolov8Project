# YOLOv8 拉流推理微服务

独立进程：拉取 RTSP → YOLOv8 推理 → Kafka `yolov8.detect.frames`（无 JPEG）。  
Kafka 不可用时才 HTTP 回调 Django `/api/inference/ingest`。  
最新 JPEG 仍写 Redis（`yolov8:frame:{cameraId}`）。  
**同一 RTSP URL 只拉流/推理一次**，结果扇出到多个 `cameraId`。

## 启动

```bash
cd yolo-service
pip install -r requirements.txt

set YOLO_WEIGHTS=D:\path\to\best.pt
set YOLO_DEVICE=cpu
set YOLO_SERVICE_PORT=8090
python run.py
```

仓库根目录也可：`pnpm run yolo`，或一键全栈 `pnpm run dev:all`。

## Django 环境

```bash
set YOLO_INFER_MODE=remote
set YOLO_SERVICE_URL=http://127.0.0.1:8090
set YOLO_INGEST_URL=http://127.0.0.1:3001/api/inference/ingest
set REDIS_URL=redis://127.0.0.1:6379/2
set KAFKA_BOOTSTRAP=127.0.0.1:9092
```

`YOLO_INFER_MODE=local` 可回退到 Django 进程内推理。

## 建议启动顺序

1. MediaMTX（RTSP/HLS）— 本机 exe 或 `docker compose up -d mediamtx`
2. `docker compose up -d rabbitmq kafka`
3. 本服务 `:8090`
4. Django `:3001`（只做 API / WS）
5. `pnpm run runtime`（Kafka 消费 + RabbitMQ 任务）
6. 前端 Vite

## 接口

- `GET /health`
- `POST /cameras/start` `{ cameraId, rtsp, conf, iou, maxDet, fps, callbackUrl, modelPath? }`
- `POST /cameras/stop` `{ cameraId }`
- `POST /cameras/stop-all`
- `POST /model/reload` `{ modelPath? }` — 热加载权重
- `GET /cameras` — 含 `shared` / `sharedWith`（同 RTSP 共用）

不可达 RTSP 连续失败后标记 `status=error` 并退避；Django 编排器会冷却后重试。

有检测框时会把 JPEG 写入 Redis（`yolov8:frame:{cameraId}`），检测 JSON 走 Kafka，不进 HTTP 热路径。

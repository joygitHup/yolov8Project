# YOLOv8 拉流推理微服务

独立进程：拉取 RTSP → YOLOv8 推理 → Kafka `yolov8.detect.frames`（无 JPEG，带 HMAC `sig`）。  
Kafka 不可用时才 HTTP 回调 Django `/api/inference/ingest`。  
最新 JPEG 仍写 Redis（`yolov8:frame:{cameraId}`）。  
**同一 RTSP URL 只拉流/推理一次**，结果扇出到多个 `cameraId`。

默认只监听 `127.0.0.1:8090`。所有 HTTP 接口都要请求头 `X-Ingest-Token`（与 Django `INGEST_TOKEN` / `backend/data/.ingest_token` 相同）。

## 启动

```bash
cd yolo-service
pip install -r requirements.txt

set YOLO_WEIGHTS=D:\path\to\best.pt
set YOLO_DEVICE=cpu
set YOLO_SERVICE_PORT=8090
set YOLO_SERVICE_HOST=127.0.0.1
set INGEST_TOKEN=<same as Django>
python run.py
```

仓库根目录也可：`pnpm run yolo`，或一键全栈 `pnpm run dev:all`。`dev:all` 会把 `.ingest_token` 注入 `INGEST_TOKEN`。

## Django 环境

```bash
set YOLO_INFER_MODE=remote
set YOLO_SERVICE_URL=http://127.0.0.1:8090
set YOLO_INGEST_URL=http://127.0.0.1:3001/api/inference/ingest
set REDIS_URL=redis://127.0.0.1:6379/2
set KAFKA_BOOTSTRAP=127.0.0.1:9092
set INGEST_TOKEN=<same secret>
```

`YOLO_INFER_MODE=local` 会被忽略；进程内推理已关闭。

## 建议启动顺序

1. MediaMTX（RTSP/HLS）— 本机 exe（runtime 拉起）或 `docker compose --profile mtx up -d mediamtx`
2. 本机已有 Rabbit/Kafka 则直接用；空机器才 `docker compose --profile mq up -d rabbitmq kafka`
3. 本服务 `127.0.0.1:8090`（带 `INGEST_TOKEN`）
4. Django `:3001`（只做 API / WS）
5. `pnpm run runtime`（Kafka 消费 + RabbitMQ 任务）
6. 前端 Vite（预览 HLS 走 `/media/mtx`，需登录 Cookie）

## 接口

全部需要 `X-Ingest-Token`：

- `GET /health`
- `POST /cameras/start` `{ cameraId, rtsp, conf, iou, maxDet, fps, callbackUrl, ingestToken?, modelPath? }`
- `POST /cameras/stop` `{ cameraId }`
- `POST /cameras/stop-all`
- `POST /model/reload` `{ modelPath? }` — 热加载权重
- `GET /cameras` — 含 `shared` / `sharedWith`（同 RTSP 共用）

不可达 RTSP 连续失败后标记 `status=error` 并退避；Django 编排器会冷却后重试。

有检测框时会把 JPEG 写入 Redis（`yolov8:frame:{cameraId}`），检测 JSON 走 Kafka（`sig` HMAC），不进 HTTP 热路径。

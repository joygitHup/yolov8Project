# AGENTS.md - YOLOv8 视频智能分析系统

## 项目概览

基于 YOLOv8 的通用型 AI 视频智能分析系统，前后端分离。前端 Vue3 + Element Plus + Vite；后端 Django DRF（默认 PostgreSQL `:5434`，`USE_SQLITE=1` 可回退）；推理由独立 **yolo-service**（FastAPI）拉 RTSP；直播预览走 MediaMTX（RTSP/HLS）。检测事件走 Kafka，后台任务走本机已有 RabbitMQ。

## 技术栈

### 前端
- Vue 3 (Composition API) + TypeScript、Vite 5、Element Plus、Vue Router 4、Pinia、Axios、Day.js、hls.js

### 后端
- Django + Django REST Framework、Channels（WebSocket，Redis 层）、PostgreSQL（`USE_SQLITE=1` 可回退）
- JWT 认证（`apps.accounts`，httpOnly Cookie `yolov8_access`，响应体不返回 token）
- Redis（Docker `:6379` / DB `2`）告警去重、任务队列、推理帧缓存
- MinIO（S3 API `:9000`，控制台 `:9001`，Bucket `yolov8pro`）抓拍、短视频、飞轮数据集

### 推理 / 流媒体
- **yolo-service**：FastAPI，RTSP 拉流 → Ultralytics YOLOv8 → `POST /api/inference/ingest`
- **MediaMTX**：RTSP `:8554`、HLS 仅本机 `127.0.0.1:8888`；浏览器经 Django `/media/mtx`（需登录 Cookie）拉取

## 目录结构

```
.
├── backend/                 # Django DRF
│   ├── apps/
│   │   ├── accounts/        # 认证 / 用户
│   │   ├── cameras/         # 摄像头
│   │   ├── alerts/          # 告警
│   │   ├── systemcfg/       # 系统配置 / 布防策略
│   │   ├── dashboard/       # 仪表盘
│   │   ├── inference/       # ingest 回调 +（可选）本地推理
│   │   ├── flywheel/        # 现场抽帧 + 标注台（reviewed 训练集）
│   │   ├── streaming/       # HLS / MediaMTX / 推流
│   │   ├── realtime/        # WebSocket
│   │   └── common/          # Redis / MinIO / 任务队列 / runtime 编排
│   ├── config/              # settings / urls
│   ├── data/                # sqlite、mediamtx yml、hls
│   └── run.py               # Django API/WS（migrate + runserver）
├── yolo-service/            # 独立 YOLO 微服务 :8090
├── src/                     # Vue3 前端
├── scripts/dev-all.ps1      # Windows 一键启动
├── docker-compose.yml       # MediaMTX（可选 yolo profile）
├── vite.config.ts
├── package.json
├── DESIGN.md
└── AGENTS.md
```

## 构建和运行

```bash
pnpm install
pip install -r backend/requirements.txt
pip install -r yolo-service/requirements.txt

# Windows 一键（MediaMTX + yolo + Django API + runtime + Vite）
pnpm run dev:all

# 或分进程
# 1) MediaMTX（本机 exe 或 docker compose up -d mediamtx）
# 2) pnpm run yolo
# 3) pnpm run server          # Django 只做 API / WebSocket
# 4) pnpm run runtime         # 编排、ffmpeg/MediaMTX 推流、取证队列、训练
# 5) set DEPLOY_RUN_PORT=3000 && pnpm run client

# 前端 + Django API + runtime（不含 YOLO / MTX）
pnpm run dev
```

常用环境变量（`DEPLOY_RUN_PORT=3000` 时前端 3000、API 3001）：

| 变量 | 含义 | 默认 |
|------|------|------|
| `DEPLOY_RUN_PORT` | 前端端口；API = +1 | `5000` |
| `YOLO_INFER_MODE` | `remote` / `local` | `remote` |
| `YOLO_SERVICE_URL` | 微服务地址 | `http://127.0.0.1:8090` |
| `YOLO_INGEST_URL` | 回调 Django | `http://127.0.0.1:3001/api/inference/ingest` |
| `YOLO_WEIGHTS` | 默认权重路径 | （见 systemcfg defaults） |
| `DEMO_RTSP_PUBLISH` | runtime 自动推演示流 | `0` |
| `MEDIAMTX_BIN` | mediamtx.exe 路径 | 脚本内猜测 |
| `INGEST_TOKEN` | ingest 鉴权（空则写入 `backend/data/.ingest_token`） | 自动生成 |
| `DJANGO_DEBUG` | Django DEBUG | `0` |
| `DJANGO_ALLOWED_HOSTS` | 允许的 Host | `localhost,127.0.0.1,[::1]` |
| `DJANGO_CORS_ORIGINS` | 额外 CORS 源（逗号分隔） | 仅本机 localhost / 127.0.0.1 |
| `REDIS_URL` | Redis（Docker，逻辑库 2） | `redis://127.0.0.1:6379/2` |
| `MINIO_ENDPOINT` | MinIO S3 API（控制台为 `:9001`） | `127.0.0.1:9000` |
| `MINIO_BUCKET` | 证据 Bucket | `yolov8pro` |
| `MINIO_ACCESS_KEY` / `SECRET` | MinIO 账号 | **必填环境变量**（仓库不写默认口令） |
| `POSTGRES_PASSWORD` | Postgres 密码 | **必填环境变量**（compose 无此变量会拒绝启动） |
| `EVIDENCE_BACKEND` | `minio` / `local` | `minio` |
| `JOBS_EMBEDDED` | runtime 进程内消费队列 | runtime=`1`，Django API=`0` |
| `JOBS_BACKEND` | 任务队列 `rabbitmq` / `redis` | `rabbitmq` |
| `RABBITMQ_URL` | RabbitMQ AMQP | 本机已有 broker：`amqp://admin:admin@127.0.0.1:5672/my_vhost` |
| `KAFKA_BOOTSTRAP` | 检测事件 Kafka | `127.0.0.1:9092`（复用已占用端口上的 kafka 容器） |
| `POSTGRES_HOST` / `PORT` | PostgreSQL | `127.0.0.1` / `5434`（compose `yolov8-postgres`；本机 5432 已被占用） |
| `USE_SQLITE` | 强制回退 SQLite | 空（默认 Postgres） |
| `DJANGO_RELOAD` | API 热重载 | `0`（默认 `--noreload`） |
| `YOLO_ALLOW_LOCAL` | 允许进程内推理 | 空（`YOLO_INFER_MODE=local` 默认忽略） |
| `KAFKA_ENABLED` | yolo/runtime 是否走 Kafka | `1` |
| `DJANGO_EMBEDDED_RUNTIME` | 把编排塞回 Django（单进程回退） | `0` |

手动推演示流示例：

```bash
ffmpeg -re -stream_loop -1 -i vide02.mp4 -c:v copy -an -f rtsp -rtsp_transport tcp rtsp://127.0.0.1:8554/mystream
```

## API 前缀

统一挂载在 `/api`（Django）。主要模块：

- **auth** — 登录 / 登出 / 个人资料 / 改密
- **cameras** — CRUD、toggle、monitor（含检测框与统一流状态：RTSP / HLS / 最近帧 / 布防）
- **alerts** — 列表、统计、处理
- **config** — settings / detection / flywheel（含 `/flywheel/samples` 标注审核）/ strategies / notification / system-info
- **dashboard** — stats、趋势、类型分布、最近告警、摄像头状态
- **users** — admin 用户管理
- **inference** — `POST /api/inference/ingest`（兼容回退；主路径是 Kafka `yolov8.detect.frames`）
- **streaming** — 预览流状态

yolo-service（默认仅监听 `127.0.0.1:8090`，请求头 `X-Ingest-Token`）：

- `GET /health`、`GET /cameras`
- `POST /cameras/start|stop`、`POST /cameras/stop-all`
- `POST /model/reload`

## 数据模型（摘要）

- **users** — 账号角色
- **cameras** — RTSP、状态、检测类型
- **alerts** — 类型/级别/框/快照
- **strategies** — 布防摄像头、类型、时段
- **system settings** — key/value JSON（detection、notification 等）

## 设计规范

详见 `DESIGN.md`：主色 `#1677ff`；大屏深色、后台浅色。

## 测试账号

| 用户名 | 密码 | 角色 |
|--------|------|------|
| admin | admin123 | 管理员 |
| operator | operator123 | 操作员 |
| viewer | viewer123 | 查看者 |

## 常见问题

### 开发端口？
`DEPLOY_RUN_PORT=3000` → Vite `3000`，Django `3001`，yolo `8090`，MediaMTX RTSP `8554` / HLS `8888`。

### 监控有流无框？
确认 yolo-service `GET /health` 的 `ready` 与 `lastCallbackOk`；检测页权重与画面类别是否匹配；布防策略是否覆盖该摄像头。

### 同 RTSP 多路摄像头？
yolo-service 按 RTSP URL 共享拉流与推理，只回调多次。

### 无效 RTSP？
连续打不开会进入 error + 冷却，避免占满 worker。离线摄像头请勿挂不可达地址（种子数据 offline 摄像头 RTSP 为空）。

### 本地推理回退？
`YOLO_INFER_MODE=local` 时由 Django 进程内推理（不推荐与 remote 同时开重负载）。

### Redis / MinIO / MQ？
使用本机已有 Docker Redis（`:6379`，逻辑库 `/2`，不要在 Windows 再装一份）。MinIO 控制台 `:9001`，对象 API `:9000`，Bucket `yolov8pro`。
检测事件走 Kafka `yolov8.detect.frames`（无 JPEG，带 HMAC `sig`），由 **runtime** 消费并写 Redis 框/图；告警落库后发 `yolov8.alerts.created`。抓拍/短视频/通知/微调走 **RabbitMQ**（`evidence` / `notify` / `flywheel`），同样由 runtime 消费。`POST /api/inference/ingest` 仅在 Kafka 不可用时由 yolo 回退。单进程兜底：`DJANGO_EMBEDDED_RUNTIME=1`。本机已有 Rabbit/Kafka 时不要 `compose up` 这两项；空机器才用 `docker compose --profile mq up -d rabbitmq kafka`。

### 现场数据集（飞轮）？
检测参数页开关采集。告警帧 + 不确定帧写入 `yolov8pro/flywheel/dataset/auto/{images,labels}`。
**标注台** `/flywheel`：改框/改类后「通过」才进入训练集。
**自学习**：在检测参数页「开始微调」。系统把已通过样本导出到 `D:\pythonDev\industrial_anomaly_detection\yolov8modle\dataset\flywheel\`，与原 `images/train` 混合，从当前 `best.pt` 增量训练。验证集 mAP50 不下降（默认允许 0.01）则热加载 yolo-service；否则保持旧权重，可回滚。训练在 **runtime** 进程排队执行，不进 Django HTTP / 推理循环。

## 开发注意事项

1. 前端请求用 `src/utils/request.ts`
2. 用户状态 Pinia `stores/user.ts`；路由守卫 `router/index.ts`
3. 检测参数里的 **模型权重** 可保存并热加载 remote 服务
4. Vite 代理 `/api`、`/media`、`/ws`（HLS 走 `/media/mtx`，不再代理 MediaMTX）
5. 登录 JWT 只放 httpOnly Cookie `yolov8_access`，不要写 localStorage
6. 详细微服务说明见 `yolo-service/README.md`

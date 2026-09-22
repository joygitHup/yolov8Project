# YOLOv8 视频智能分析系统 — 需求文档（当前版本）

| 项 | 内容 |
|----|------|
| 文档版本 | v1.0（当前发行版） |
| 适用范围 | 前端 Vue3、后端 Django DRF、推理微服务 yolo-service、流媒体 MediaMTX |
| 编制日期 | 2026-09-21 |
| 关联文档 | `AGENTS.md`、`DESIGN.md`、`docs/售前方案-YOLOv8视频智能分析系统.md` |

---

## 1. 项目背景

### 1.1 业务背景
园区、交通枢纽、厂区等场景长期依赖人工值守 CCTV，存在以下痛点：
- 人力成本高、夜班疲劳导致漏报；
- 告警事件事后追溯效率低，证据链不完整；
- 传统移动侦测/简单算法误报率高，无法识别具体目标类型；
- 现场样本难以回流到模型，AI 能力无法持续进化。

### 1.2 建设目标
构建一套基于 YOLOv8 的通用型 AI 视频智能分析系统，实现：
1. 多路 RTSP 视频接入、AI 实时识别、可视化监控；
2. 告警事件闭环管理（发现 → 推送 → 处置 → 留痕）；
3. 现场"飞轮"自学习：自动采集 → 人工标注 → 增量训练 → 热加载；
4. 数据大屏与后台管理双形态，适配指挥中心与日常运营；
5. 微服务化部署，易于横向扩展。

### 1.3 适用范围
- 园区安防（周界入侵、违规停放、人员聚集）
- 交通枢纽（客流统计、车牌识别扩展、违停）
- 工业厂区（安全帽/工服合规、设备区域入侵）
- 仓储物流（火苗/烟雾、人员闯入）

---

## 2. 目标用户与角色权限

### 2.1 角色定义

| 角色 | 标识 | 主要职责 |
|------|------|----------|
| 管理员 | `admin` | 用户/权限、系统配置、布防策略、模型权重管理、飞轮训练 |
| 操作员 | `operator` | 摄像头运维、实时监控、告警处置、样本审核 |
| 查看者 | `viewer` | 大屏、监控、告警列表只读 |

### 2.2 测试账号

| 用户名 | 密码 | 角色 |
|--------|------|------|
| admin | admin123 | 管理员 |
| operator | operator123 | 操作员 |
| viewer | viewer123 | 查看者 |

### 2.3 权限矩阵（摘要）

| 模块 | admin | operator | viewer |
|------|:----:|:----:|:----:|
| 数据大屏 | R | R | R |
| 实时监控 | R | R | R |
| 摄像头 CRUD | RW | RW | R |
| 布防策略 | RW | R | R |
| 告警处置 | RW | RW | R |
| 用户管理 | RW | - | - |
| 系统配置 | RW | - | - |
| 飞轮标注台 | RW | RW | - |
| 模型热加载/微调 | RW | - | - |

> R = 只读，RW = 读写

### 2.4 认证机制
- JWT 登录后写入 httpOnly Cookie `yolov8_access`，响应体不返回 token；
- 前端 Axios 自动携带 Cookie；未登录访问受保护路由静默重定向至 `/login`；
- 退出登录调用 `POST /api/auth/logout` 清除 Cookie 后再跳转；
- 推理微服务与 ingest 回调使用独立 `X-Ingest-Token` 头鉴权。

---

## 3. 功能需求

### 3.1 数据大屏（Dashboard）
**目标**：指挥中心一屏总览全局态势。

- 顶部 KPI：在线摄像头数、今日告警数、未处置告警、模型版本；
- 趋势图：近 7/30 日告警趋势折线；
- 类型分布：告警类型饼图（入侵/违停/火警/聚集等）；
- 摄像头状态：在线/离线/推理中分布；
- 最近告警流水（含快照缩略图）；
- 深色主题，背景 `#0a0e17`，数字字体 JetBrains Mono；
- 自动刷新（默认 30s，可配置）。

**接口**：`GET /api/dashboard/stats`、`/api/dashboard/trends`、`/api/dashboard/type-distribution`、`/api/dashboard/recent-alerts`、`/api/dashboard/camera-status`。

### 3.2 总览分析
- 时间区间筛选的告警聚合视图；
- 按摄像头/类型/级别的多维交叉统计；
- 支持导出 CSV/Excel（v1.0 仅 CSV）。

### 3.3 实时监控（Monitor）
- 左侧摄像头树（按区域分组）；
- 右侧多画面网格（1/4/9 宫格）；
- 单画面支持：HLS 播放、检测框叠加、LIVE 角标、布防状态；
- 控制：单路启动/停止、批量启动、快照、手动录像；
- 走 MediaMTX 原生 HLS，经 Django `/media/mtx/<path>/<file>` 代理（带 Cookie 鉴权）；
- WebSocket `/ws/realtime/` 推送检测帧元数据（框、类型、置信度）。

**接口**：`GET /api/cameras`、`GET /api/cameras/{id}/monitor`、`POST /api/cameras/{id}/stream/start`、`POST /api/cameras/{id}/stream/stop`。

### 3.4 摄像头管理（Cameras）
- 字段：名称、RTSP URL、区域、经纬度（可选）、检测类型集合、布防开关、状态、权重覆盖；
- CRUD + 启用/停用 + 一键测试拉流；
- 状态机：`online / offline / error / cooldown`；
- 同一 RTSP 多路摄像头共享拉流与推理，只回调多次；
- 无效 RTSP 连续失败进入 `error + 冷却`，避免占满 worker；
- 离线种子摄像头 RTSP 留空。

**接口**：`GET/POST /api/cameras`、`GET/PUT/DELETE /api/cameras/{id}`、`POST /api/cameras/{id}/toggle`、`GET /api/cameras/{id}/monitor`。

### 3.5 报警中心（Alerts）
- 列表：时间、摄像头、类型、级别、状态、快照；
- 筛选：时间区间、级别、类型、摄像头、状态；
- 详情：原图 + 检测框、置信度、处置记录；
- 处置：确认（误报/真实）、忽略、指派、备注；
- 告警去重：Redis 维护 (camera, type, bbox) 短窗口去重；
- 告警落库后向 Kafka `yolov8.alerts.created` 发布事件。

**接口**：`GET /api/alerts`、`GET /api/alerts/{id}`、`POST /api/alerts/{id}/handle`、`GET /api/alerts/stats`。

### 3.6 系统配置（SystemCfg）
- 检测参数：默认权重、置信度阈值、IoU、输入尺寸、类别白名单；
- 通知参数：Webhook、邮件、飞书/钉钉机器人；
- 布防策略（Strategies）：摄像头 × 类型 × 时段；
- 系统信息：版本、模型、运行模式、队列状态；
- 模型权重热加载（remote yolo-service）。

**接口**：`GET/PUT /api/config/settings`、`/api/config/detection`、`/api/config/strategies`、`/api/config/notification`、`/api/config/system-info`、`POST /api/config/model/reload`。

### 3.7 飞轮标注台（Flywheel）
- 自动数据集：检测参数页开启采集后，告警帧 + 不确定帧写入 MinIO `yolov8pro/flywheel/dataset/auto/{images,labels}`；
- 标注台 `/flywheel`：列样本 → 改框/改类 → "通过"才进入训练集；
- 样本查询：按置信度区间、类别、摄像头、时间；
- 审核 API：`GET /api/config/flywheel/samples`、`POST /api/config/flywheel/samples/{id}/review`。

### 3.8 自学习与微调（Flywheel Training）
- 在检测参数页点"开始微调"；
- runtime 将已通过样本导出到 `D:\pythonDev\industrial_anomaly_detection\yolov8modle\dataset\flywheel\`，与原 `images/train` 混合；
- 从当前 `best.pt` 增量训练；
- 验证集 mAP50 不下降（默认允许 0.01）则热加载 yolo-service；否则保持旧权重，可回滚；
- 训练在 **runtime** 进程排队执行，不进 Django HTTP / 推理循环。

### 3.9 用户管理（Users，仅 admin）
- 列表/新增/编辑/停用/重置密码；
- 角色分配；
- 操作日志（v1.0 仅写入 DB，不提供前端查询）。

**接口**：`GET/POST /api/users`、`PUT/PATCH /api/users/{id}`、`POST /api/users/{id}/reset-password`。

### 3.10 检测引擎（yolo-service）
独立 FastAPI 微服务，默认 `127.0.0.1:8090`：

- `GET /health` — 返回 `ready`、模型、最近回调状态 `lastCallbackOk`；
- `GET /cameras` — 列出当前推理中的摄像头；
- `POST /cameras/start` — 启动某路 RTSP 推理（请求头 `X-Ingest-Token`）；
- `POST /cameras/stop` — 停止；
- `POST /cameras/stop-all` — 停止全部；
- `POST /model/reload` — 热加载权重。

推理结果主路径走 Kafka `yolov8.detect.frames`（无 JPEG，带 HMAC `sig`），由 runtime 消费并写 Redis 框/图；Kafka 不可用时由 yolo 回退 `POST /api/inference/ingest`。

---

## 4. 非功能需求

### 4.1 性能
- 单路 1080p 推理延迟 ≤ 200ms（GPU，YOLOv8m）；
- 单卡支持并发 8~16 路（依权重与 GPU）；
- HLS 端到端延迟 ≤ 3s；
- 告警从产生到落库 ≤ 1s，到推送 ≤ 3s；
- 大屏接口 P95 ≤ 800ms。

### 4.2 可用性
- MediaMTX 进程被 runtime 拉起，崩了自动重启；
- RabbitMQ/Redis/Kafka 任一外部中间件不可用不阻塞主推理路径，回退到 Redis 队列；
- 离线摄像头进入冷却，不占 worker；
- `DJANGO_EMBEDDED_RUNTIME=1` 支持单进程兜底部署。

### 4.3 安全
- 所有 Django 接口必须 JWT 鉴权（除 `/api/auth/login`、`/api/health`、`/api/inference/ingest` 走 token）；
- HLS 代理走 Cookie 鉴权，不直接暴露 MediaMTX :8888；
- ingest 回调走 `X-Ingest-Token` + HMAC `sig`；
- MinIO 凭据走环境变量，不写入仓库；
- 输入校验在 DRF Serializer / DRF View 边界完成。

### 4.4 兼容性
- 浏览器：Chrome ≥ 100、Edge ≥ 100、Firefox ≥ 100（需支持 HLS via hls.js）；
- 操作系统：Windows 10/11、Linux（Ubuntu 20.04+）；
- GPU：CUDA 11.8+ / 12.x（可选，CPU 可跑但性能受限）。

### 4.5 可维护性
- 前端统一通过 `src/utils/request.ts` 发请求，统一错误处理；
- 后端按 `apps/<domain>` 分模块，公共能力在 `apps/common`；
- 关键路径有日志（streaming mediamtx、inference ingest、runtime queue）；
- 配置走环境变量 + `apps/systemcfg` 表，无需改代码。

---

## 5. 数据模型（摘要）

| 实体 | 关键字段 | 说明 |
|------|---------|------|
| users | id, username, password, role, is_active, created_at | 账号角色 |
| cameras | id, name, rtsp, region, lng, lat, detection_types, enabled, status, weights | 摄像头 |
| alerts | id, camera_id, type, level, bbox, snapshot, status, handled_by, handled_at, created_at | 告警 |
| strategies | id, camera_id, detection_types, time_window, enabled | 布防策略 |
| system_settings | key, value(JSON) | 系统配置（detection/notification/flywheel） |
| flywheel_samples | id, camera_id, image_path, label, confidence, reviewed, source | 飞轮样本 |

> 默认数据库 PostgreSQL（`127.0.0.1:5434`，DB `yolov8pro`），`USE_SQLITE=1` 回退 SQLite（`backend/data/sqlite`）。

---

## 6. 接口规范

### 6.1 统一约定
- 前缀：`/api`；
- 鉴权：httpOnly Cookie `yolov8_access`；
- 错误响应：`{ "error": "<message>" }`，HTTP 状态码符合语义；
- 列表分页：`?page=<n>&page_size=<n>`，响应 `{ results: [], total, page, page_size }`。

### 6.2 主要模块

| 模块 | 路径前缀 | 说明 |
|------|----------|------|
| auth | `/api/auth` | login / logout / me / change-password |
| cameras | `/api/cameras` | CRUD / monitor / toggle |
| alerts | `/api/alerts` | 列表、详情、处置、统计 |
| config | `/api/config` | settings / detection / strategies / notification / system-info / flywheel |
| dashboard | `/api/dashboard` | stats / trends / type-distribution / recent-alerts / camera-status |
| users | `/api/users` | 用户管理（admin） |
| inference | `/api/inference` | `POST /ingest`（回退路径） |
| streaming | `/api/streaming` | 预览流状态 |
| media | `/media/hls`、`/media/mtx`、`/media/alerts` | HLS / MediaMTX 代理 / 告警媒体 |
| realtime | `/ws/realtime/` | WebSocket 检测帧推送 |

### 6.3 yolo-service 接口
见 3.10。

---

## 7. 运行环境

### 7.1 端口规划（`DEPLOY_RUN_PORT=3000` 示例）

| 服务 | 端口 | 说明 |
|------|------|------|
| 前端 Vite | 3000 | 默认 5000 |
| Django API / WS | 3001 | `DEPLOY_RUN_PORT+1` |
| yolo-service | 8090 | 仅 `127.0.0.1` |
| MediaMTX RTSP | 8554 | |
| MediaMTX HLS | 8888 | 仅本机，浏览器走 Django 代理 |
| PostgreSQL | 5434 | compose `yolov8-postgres` |
| Redis | 6379 | DB 2 |
| MinIO S3 / 控制台 | 9000 / 9001 | Bucket `yolov8pro` |
| RabbitMQ AMQP | 5672 | `amqp://yolov8:yolov8@127.0.0.1:5672/` |
| Kafka | 9092 | topic `yolov8.detect.frames` / `yolov8.alerts.created` |

### 7.2 关键环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| DEPLOY_RUN_PORT | 5000 | 前端端口；API = +1 |
| YOLO_INFER_MODE | remote | remote / local |
| YOLO_SERVICE_URL | http://127.0.0.1:8090 | 微服务地址 |
| YOLO_INGEST_URL | http://127.0.0.1:3001/api/inference/ingest | 回调 |
| YOLO_WEIGHTS | 见 systemcfg defaults | 默认权重 |
| DEMO_RTSP_PUBLISH | 0 | runtime 自动推演示流 |
| MEDIAMTX_BIN | 脚本内猜测 | mediamtx.exe 路径 |
| INGEST_TOKEN | 自动生成 | ingest 鉴权 |
| DJANGO_DEBUG | 0 | Django DEBUG |
| DJANGO_ALLOWED_HOSTS | localhost,127.0.0.1,[::1] | |
| DJANGO_CORS_ORIGINS | 本机 localhost / 127.0.0.1 | |
| REDIS_URL | redis://127.0.0.1:6379/2 | |
| MINIO_ENDPOINT | 127.0.0.1:9000 | |
| MINIO_BUCKET | yolov8pro | |
| MINIO_ACCESS_KEY / SECRET | **必填** | |
| POSTGRES_PASSWORD | **必填** | |
| EVIDENCE_BACKEND | minio | minio / local |
| JOBS_EMBEDDED | runtime=1，Django API=0 | runtime 进程内消费队列 |
| JOBS_BACKEND | rabbitmq | rabbitmq / redis |
| RABBITMQ_URL | amqp://yolov8:yolov8@127.0.0.1:5672/ | |
| KAFKA_BOOTSTRAP | 127.0.0.1:9092 | |
| POSTGRES_HOST / PORT | 127.0.0.1 / 5434 | |
| USE_SQLITE | 空 | 强制回退 SQLite |
| DJANGO_RELOAD | 0 | API 热重载 |
| YOLO_ALLOW_LOCAL | 空 | 允许进程内推理 |
| KAFKA_ENABLED | 1 | yolo/runtime 是否走 Kafka |
| DJANGO_EMBEDDED_RUNTIME | 0 | 单进程兜底 |

### 7.3 一键启动
```powershell
pnpm install
pnpm run dev:all   # MediaMTX + yolo + Django API + runtime + Vite
```

分进程启动顺序：
1. MediaMTX（exe 或 `docker compose up -d mediamtx`）；
2. `pnpm run yolo`；
3. `pnpm run server`（Django API / WS）；
4. `pnpm run runtime`（编排、ffmpeg/MediaMTX 推流、取证队列、训练）；
5. `pnpm run client`（Vite）。

手动推演示流示例：
```bash
ffmpeg -re -stream_loop -1 -i video1.mp4 -c:v copy -an -f rtsp -rtsp_transport tcp rtsp://127.0.0.1:8554/mystream
```

---

## 8. 依赖服务

| 组件 | 用途 | 必需 |
|------|------|------|
| PostgreSQL | 业务数据 | 是（或 SQLite 回退） |
| Redis | 告警去重、任务队列、推理帧缓存、WebSocket 层 | 是 |
| MinIO | 抓拍、短视频、飞轮数据集 | 是（或 local） |
| RabbitMQ | 抓拍/通知/飞轮任务队列 | 是（或 redis） |
| Kafka | 检测事件流、告警事件流 | 推荐（可回退 ingest） |
| MediaMTX | RTSP / HLS 流媒体 | 是 |
| ffmpeg | HLS remux、推流 | 是 |
| CUDA GPU | 推理加速 | 否（CPU 可跑） |

---

## 9. 验收准则（当前版本）

1. 三种角色登录后能看到对应权限的菜单与功能；
2. 未登录访问受保护页面应静默重定向到 `/login`；
3. 配置好 RTSP 的摄像头在监控页能显示画面 + 检测框 + LIVE 角标；
4. 同一 RTSP 多路摄像头共享拉流，回调多次；
5. 无效 RTSP 进入 error + 冷却，不影响其他路；
6. 告警能从产生 → 落库 → 处置 → 留痕全流程闭环；
7. 飞轮标注台"通过"的样本进入训练集；微调 mAP50 不下降则热加载；
8. 大屏接口 P95 ≤ 800ms，HLS 端到端延迟 ≤ 3s；
9. MediaMTX 进程崩溃后由 runtime 自动拉起；
10. RabbitMQ/Redis/Kafka 任一外部中间件不可用不阻塞主推理路径。

---

## 10. 名词表

| 名词 | 说明 |
|------|------|
| 飞轮自学习 | 自动采集 → 标注台 → 增量训练 → 热加载的闭环 |
| 布防策略 | 摄像头 × 检测类型 × 时段的启停规则 |
| ingest 回调 | yolo-service 检测结果回写 Django 的 HTTP 兜底路径 |
| runtime | 独立后台进程，负责编排、推流、取证队列、训练 |
| master/sub playlist | HLS 主/子播放列表，MediaMTX 通过 `?session=` 区分 |
| cookieCheck | MediaMTX 对 HLS 首次请求的 302 重定向 + Set-Cookie 机制 |

# One-click local stack (Windows PowerShell)
# Starts: MediaMTX -> yolo-service -> Django (API/WS) -> runtime (jobs/ffmpeg/train) -> Vite
#
# Usage:
#   pwsh -File scripts/dev-all.ps1
#   pnpm run dev:all
#
# Env overrides:
#   DEPLOY_RUN_PORT=3000
#   YOLO_WEIGHTS=D:\path\to\best.pt
#   MEDIAMTX_BIN=D:\applicationPath\ffmpegPath\mediamtx.exe
#   DEMO_VIDEO=D:\applicationPath\ffmpegPath\vide02.mp4

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$port = if ($env:DEPLOY_RUN_PORT) { [int]$env:DEPLOY_RUN_PORT } else { 3000 }
$apiPort = $port + 1
$yoloPort = if ($env:YOLO_SERVICE_PORT) { [int]$env:YOLO_SERVICE_PORT } else { 8090 }

$env:DEPLOY_RUN_PORT = "$port"
$env:YOLO_INFER_MODE = if ($env:YOLO_INFER_MODE) { $env:YOLO_INFER_MODE } else { "remote" }
$env:YOLO_SERVICE_URL = if ($env:YOLO_SERVICE_URL) { $env:YOLO_SERVICE_URL } else { "http://127.0.0.1:$yoloPort" }
$env:YOLO_INGEST_URL = if ($env:YOLO_INGEST_URL) { $env:YOLO_INGEST_URL } else { "http://127.0.0.1:$apiPort/api/inference/ingest" }
$env:DEMO_RTSP_PUBLISH = if ($env:DEMO_RTSP_PUBLISH) { $env:DEMO_RTSP_PUBLISH } else { "0" }
$env:MEDIAMTX_HLS_BASE = if ($env:MEDIAMTX_HLS_BASE) { $env:MEDIAMTX_HLS_BASE } else { "http://127.0.0.1:8888" }

$tokenFile = Join-Path $Root "backend\data\.ingest_token"
if (-not $env:INGEST_TOKEN) {
  if (Test-Path $tokenFile) {
    $env:INGEST_TOKEN = (Get-Content -Path $tokenFile -Raw -ErrorAction SilentlyContinue).Trim()
  }
  if (-not $env:INGEST_TOKEN) {
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $bytes = New-Object byte[] 32
    $rng.GetBytes($bytes)
    $env:INGEST_TOKEN = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
    New-Item -ItemType Directory -Force -Path (Split-Path $tokenFile) | Out-Null
    Set-Content -Path $tokenFile -Value $env:INGEST_TOKEN -NoNewline -Encoding ascii
  }
}
$env:REDIS_URL = if ($env:REDIS_URL) { $env:REDIS_URL } else { "redis://127.0.0.1:6379/2" }
$env:MINIO_ENDPOINT = if ($env:MINIO_ENDPOINT) { $env:MINIO_ENDPOINT } else { "127.0.0.1:9000" }
$env:MINIO_BUCKET = if ($env:MINIO_BUCKET) { $env:MINIO_BUCKET } else { "yolov8pro" }
$env:MINIO_ACCESS_KEY = if ($env:MINIO_ACCESS_KEY) { $env:MINIO_ACCESS_KEY } else { "Admin" }
$env:MINIO_SECRET_KEY = if ($env:MINIO_SECRET_KEY) { $env:MINIO_SECRET_KEY } else { "Admin123" }
$env:RABBITMQ_URL = if ($env:RABBITMQ_URL) { $env:RABBITMQ_URL } else { "amqp://admin:admin@127.0.0.1:5672/my_vhost" }
$env:KAFKA_BOOTSTRAP = if ($env:KAFKA_BOOTSTRAP) { $env:KAFKA_BOOTSTRAP } else { "127.0.0.1:9092" }
$env:POSTGRES_HOST = if ($env:POSTGRES_HOST) { $env:POSTGRES_HOST } else { "127.0.0.1" }
$env:POSTGRES_PORT = if ($env:POSTGRES_PORT) { $env:POSTGRES_PORT } else { "5434" }
$env:POSTGRES_DB = if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { "yolov8" }
$env:POSTGRES_USER = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "yolov8" }
$env:POSTGRES_PASSWORD = if ($env:POSTGRES_PASSWORD) { $env:POSTGRES_PASSWORD } else { "yolov8" }

# Reuse brokers already bound on this machine. Do not `docker compose up` rabbitmq/kafka
# (those compose services are profile `mq` and would collide with :5672 / :9092).
try { docker start redis | Out-Null; Write-Host "[redis] existing container 'redis'" } catch { Write-Warning "start redis failed" }
try { docker start rabbitmq-new | Out-Null; Write-Host "[rabbit] existing container 'rabbitmq-new' :5672" } catch { Write-Host "[rabbit] using whatever is on :5672 ($($env:RABBITMQ_URL))" }
try { docker start kafka | Out-Null; Write-Host "[kafka] existing container 'kafka' :9092" } catch { Write-Host "[kafka] using :9092" }
try {
  docker compose up -d postgres | Out-Null
  Write-Host "[postgres] yolov8-postgres :5434"
} catch {
  Write-Warning "docker compose postgres failed. Set USE_SQLITE=1 or start yolov8-postgres."
}

if (-not $env:YOLO_WEIGHTS) {
  $candidates = @(
    "D:\pythonDev\industrial_anomaly_detection\yolov8modle\runs\detect\train-6\weights\best.pt",
    "D:\pythonDev\industrial_anomaly_detection\yolov8modle\runs\detect\runs\train\my_model-2\weights\best.pt",
    "D:\pythonDev\industrial_anomaly_detection\yolov8modle\runs\detect\runs\train\my_model-4\weights\best.pt"
  )
  foreach ($c in $candidates) {
    if (Test-Path $c) { $env:YOLO_WEIGHTS = $c; break }
  }
}

function Test-PortOpen([int]$PortNum) {
  try {
    $c = New-Object System.Net.Sockets.TcpClient
    $iar = $c.BeginConnect("127.0.0.1", $PortNum, $null, $null)
    $ok = $iar.AsyncWaitHandle.WaitOne(400)
    if ($ok -and $c.Connected) { $c.Close(); return $true }
    $c.Close()
  } catch {}
  return $false
}

# MediaMTX is started by runtime (apps.streaming.mediamtx.ensure_running).
# Opt-in docker: MEDIAMTX_MODE=docker  or  docker compose --profile mtx up -d mediamtx
if (Test-PortOpen 8554) {
  Write-Host "[mtx] already listening on 8554 (runtime will reuse)"
} else {
  Write-Host "[mtx] port 8554 closed; runtime process will start MediaMTX"
}

# Optional demo push (only if DEMO_RTSP_PUBLISH=1 and DEMO_VIDEO set)
$demoVideo = $env:DEMO_VIDEO
if ($env:DEMO_RTSP_PUBLISH -eq "1" -and $demoVideo -and (Test-Path $demoVideo)) {
  $ff = if ($env:FFMPEG_BIN) { $env:FFMPEG_BIN } else { "ffmpeg" }
  Write-Host "[ffmpeg] looping push $demoVideo -> rtsp://127.0.0.1:8554/mystream"
  Start-Process -FilePath $ff -ArgumentList @(
    "-re", "-stream_loop", "-1", "-i", $demoVideo,
    "-c:v", "copy", "-an", "-f", "rtsp", "-rtsp_transport", "tcp",
    "rtsp://127.0.0.1:8554/mystream"
  ) -WindowStyle Minimized
}

Write-Host "[env] DEPLOY_RUN_PORT=$port  YOLO=$($env:YOLO_SERVICE_URL)  mode=$($env:YOLO_INFER_MODE)"
Write-Host "[env] YOLO_WEIGHTS=$($env:YOLO_WEIGHTS)"
Write-Host "[run] yolo :$yoloPort | django :$apiPort | runtime | vite :$port"

$yoloCmd = "cd `"$Root\yolo-service`"; `$env:YOLO_WEIGHTS='$($env:YOLO_WEIGHTS)'; `$env:YOLO_SERVICE_PORT='$yoloPort'; `$env:YOLO_SERVICE_HOST='127.0.0.1'; `$env:REDIS_URL='$($env:REDIS_URL)'; `$env:KAFKA_BOOTSTRAP='127.0.0.1:9092'; `$env:KAFKA_ENABLED='1'; `$env:INGEST_TOKEN='$($env:INGEST_TOKEN)'; python run.py"
$djCmd = "cd `"$Root`"; `$env:DEPLOY_RUN_PORT='$port'; `$env:YOLO_INFER_MODE='$($env:YOLO_INFER_MODE)'; `$env:YOLO_SERVICE_URL='$($env:YOLO_SERVICE_URL)'; `$env:YOLO_INGEST_URL='$($env:YOLO_INGEST_URL)'; `$env:DEMO_RTSP_PUBLISH='$($env:DEMO_RTSP_PUBLISH)'; `$env:YOLO_WEIGHTS='$($env:YOLO_WEIGHTS)'; `$env:REDIS_URL='$($env:REDIS_URL)'; `$env:MINIO_ENDPOINT='$($env:MINIO_ENDPOINT)'; `$env:MINIO_BUCKET='$($env:MINIO_BUCKET)'; `$env:MINIO_ACCESS_KEY='$($env:MINIO_ACCESS_KEY)'; `$env:MINIO_SECRET_KEY='$($env:MINIO_SECRET_KEY)'; `$env:JOBS_EMBEDDED='0'; `$env:DJANGO_EMBEDDED_RUNTIME='0'; `$env:JOBS_BACKEND='rabbitmq'; `$env:RABBITMQ_URL='$($env:RABBITMQ_URL)'; `$env:KAFKA_BOOTSTRAP='$($env:KAFKA_BOOTSTRAP)'; `$env:POSTGRES_HOST='$($env:POSTGRES_HOST)'; `$env:POSTGRES_PORT='$($env:POSTGRES_PORT)'; `$env:POSTGRES_DB='$($env:POSTGRES_DB)'; `$env:POSTGRES_USER='$($env:POSTGRES_USER)'; `$env:POSTGRES_PASSWORD='$($env:POSTGRES_PASSWORD)'; `$env:INGEST_TOKEN='$($env:INGEST_TOKEN)'; python backend/run.py"
$rtCmd = "cd `"$Root`"; `$env:DEPLOY_RUN_PORT='$port'; `$env:YOLO_INFER_MODE='$($env:YOLO_INFER_MODE)'; `$env:YOLO_SERVICE_URL='$($env:YOLO_SERVICE_URL)'; `$env:YOLO_INGEST_URL='$($env:YOLO_INGEST_URL)'; `$env:DEMO_RTSP_PUBLISH='$($env:DEMO_RTSP_PUBLISH)'; `$env:YOLO_WEIGHTS='$($env:YOLO_WEIGHTS)'; `$env:REDIS_URL='$($env:REDIS_URL)'; `$env:MINIO_ENDPOINT='$($env:MINIO_ENDPOINT)'; `$env:MINIO_BUCKET='$($env:MINIO_BUCKET)'; `$env:MINIO_ACCESS_KEY='$($env:MINIO_ACCESS_KEY)'; `$env:MINIO_SECRET_KEY='$($env:MINIO_SECRET_KEY)'; `$env:JOBS_EMBEDDED='1'; `$env:JOBS_BACKEND='rabbitmq'; `$env:RABBITMQ_URL='$($env:RABBITMQ_URL)'; `$env:KAFKA_BOOTSTRAP='$($env:KAFKA_BOOTSTRAP)'; `$env:POSTGRES_HOST='$($env:POSTGRES_HOST)'; `$env:POSTGRES_PORT='$($env:POSTGRES_PORT)'; `$env:POSTGRES_DB='$($env:POSTGRES_DB)'; `$env:POSTGRES_USER='$($env:POSTGRES_USER)'; `$env:POSTGRES_PASSWORD='$($env:POSTGRES_PASSWORD)'; `$env:INGEST_TOKEN='$($env:INGEST_TOKEN)'; python backend/manage.py run_runtime"
$viteCmd = "cd `"$Root`"; `$env:DEPLOY_RUN_PORT='$port'; `$env:MEDIAMTX_HLS_BASE='$($env:MEDIAMTX_HLS_BASE)'; pnpm run client"

# Prefer concurrently if available via pnpm
npx --yes concurrently -k -n "YOLO,DJANGO,RUNTIME,VITE" -c "magenta,blue,cyan,green" `
  "powershell -NoProfile -Command $yoloCmd" `
  "powershell -NoProfile -Command $djCmd" `
  "powershell -NoProfile -Command $rtCmd" `
  "powershell -NoProfile -Command $viteCmd"

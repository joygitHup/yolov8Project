import os
import time
from pathlib import Path
from datetime import timedelta

from corsheaders.defaults import default_headers

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

def _secret_key() -> str:
    env = (os.environ.get("DJANGO_SECRET_KEY") or "").strip()
    if env:
        return env
    path = DATA_DIR / ".secret_key"
    try:
        if path.is_file():
            text = path.read_text(encoding="utf-8").strip()
            if text:
                return text
    except OSError:
        pass
    import secrets

    key = secrets.token_urlsafe(48)
    try:
        path.write_text(key, encoding="utf-8")
    except OSError:
        pass
    return key


os.environ.setdefault("ASGI_THREADS", "16")
os.environ.setdefault("DJANGO_ASGI_THREADS", "16")

SECRET_KEY = _secret_key()
DEBUG = os.environ.get("DJANGO_DEBUG", "0").strip().lower() in ("1", "true", "yes", "on")
_hosts = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").strip()
ALLOWED_HOSTS = [h.strip() for h in _hosts.split(",") if h.strip()] or ["localhost", "127.0.0.1"]


def _ingest_token() -> str:
    env = (os.environ.get("INGEST_TOKEN") or "").strip()
    if env:
        return env
    path = DATA_DIR / ".ingest_token"
    try:
        if path.is_file():
            text = path.read_text(encoding="utf-8").strip()
            if text:
                return text
    except OSError:
        pass
    import secrets

    token = secrets.token_urlsafe(32)
    try:
        path.write_text(token, encoding="utf-8")
    except OSError:
        pass
    return token


INGEST_TOKEN = _ingest_token()

INSTALLED_APPS = [
    "daphne",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "channels",
    "apps.accounts",
    "apps.cameras",
    "apps.alerts.apps.AlertsConfig",
    "apps.systemcfg",
    "apps.dashboard",
    "apps.inference.apps.InferenceConfig",
    "apps.flywheel.apps.FlywheelConfig",
    "apps.realtime",
    "apps.streaming.apps.StreamingConfig",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
APPEND_SLASH = False

# PostgreSQL on :5434 (compose yolov8-postgres). :5432 is already taken on this machine.
# Set USE_SQLITE=1 to fall back to backend/data/db.sqlite3.
_use_sqlite = os.environ.get("USE_SQLITE", "").strip().lower() in ("1", "true", "yes", "on")
_pg_host = os.environ.get("POSTGRES_HOST") or os.environ.get("PGHOST")
if not _use_sqlite:
    _pg_host = _pg_host or "127.0.0.1"
if _pg_host and not _use_sqlite:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("POSTGRES_DB", "yolov8"),
            "USER": os.environ.get("POSTGRES_USER", "yolov8"),
            "PASSWORD": os.environ.get("POSTGRES_PASSWORD") or os.environ.get("PGPASSWORD") or "",
            "HOST": _pg_host,
            "PORT": os.environ.get("POSTGRES_PORT") or os.environ.get("PGPORT") or "5434",
            "CONN_MAX_AGE": 60,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": DATA_DIR / "db.sqlite3",
            "OPTIONS": {"timeout": 20},
        }
    }

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

_cors = [x.strip() for x in os.environ.get("DJANGO_CORS_ORIGINS", "").split(",") if x.strip()]
if _cors:
    CORS_ALLOWED_ORIGINS = _cors
else:
    CORS_ALLOWED_ORIGIN_REGEXES = [
        r"^https?://localhost(:\d+)?$",
        r"^https?://127\.0\.0\.1(:\d+)?$",
        r"^https?://\[::1\](:\d+)?$",
    ]
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = list(default_headers) + [
    "authorization",
    "x-ingest-token",
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "apps.accounts.authentication.JWTHeaderOrCookieAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "EXCEPTION_HANDLER": "apps.common.exceptions.api_exception_handler",
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "DATETIME_FORMAT": None,
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=24),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

STARTED_AT = time.time()

# Redis: reuse the existing Docker instance on :6379, dedicated logical DB 2.
REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/2")
REDIS_PREFIX = os.environ.get("REDIS_PREFIX", "yolov8")

# MinIO: S3 API is :9000; console (browser) is :9001. Bucket already provisioned.
MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "127.0.0.1:9000")
MINIO_ACCESS_KEY = (os.environ.get("MINIO_ACCESS_KEY") or "").strip()
MINIO_SECRET_KEY = (os.environ.get("MINIO_SECRET_KEY") or "").strip()
MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "yolov8pro")
MINIO_SECURE = os.environ.get("MINIO_SECURE", "0") not in ("0", "false", "no", "off")
EVIDENCE_BACKEND = os.environ.get("EVIDENCE_BACKEND", "minio").strip().lower() or "minio"

# Job queue: consumed by `manage.py run_runtime` (not the HTTP process).
# Set DJANGO_EMBEDDED_RUNTIME=1 / JOBS_EMBEDDED=1 only for a single-process fallback.
JOBS_EMBEDDED = os.environ.get("JOBS_EMBEDDED", "0") not in ("0", "false", "no", "off")
JOBS_SYNC = os.environ.get("JOBS_SYNC", "0") in ("1", "true", "yes", "on")
JOBS_WORKERS = max(1, min(int(os.environ.get("JOBS_WORKERS", "2") or 2), 8))
JOBS_BACKEND = (os.environ.get("JOBS_BACKEND") or "rabbitmq").strip().lower() or "rabbitmq"
# Reuse the broker already listening on :5672 (this machine: rabbitmq-new, vhost my_vhost).
RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://admin:admin@127.0.0.1:5672/my_vhost")
KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "127.0.0.1:9092")
KAFKA_ENABLED = os.environ.get("KAFKA_ENABLED", "1") not in ("0", "false", "no", "off")
KAFKA_TOPIC_FRAMES = os.environ.get("KAFKA_TOPIC_FRAMES", "yolov8.detect.frames")
KAFKA_TOPIC_ALERTS = os.environ.get("KAFKA_TOPIC_ALERTS", "yolov8.alerts.created")


def _redis_channel_layer():
    try:
        import redis as redis_lib
        import channels_redis.core  # noqa: F401

        client = redis_lib.Redis.from_url(REDIS_URL, socket_connect_timeout=1)
        client.ping()
        return {
            "default": {
                "BACKEND": "channels_redis.core.RedisChannelLayer",
                "CONFIG": {"hosts": [REDIS_URL]},
            }
        }
    except Exception:
        return {
            "default": {
                "BACKEND": "channels.layers.InMemoryChannelLayer",
            }
        }


CHANNEL_LAYERS = _redis_channel_layer()

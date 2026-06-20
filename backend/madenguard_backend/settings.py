"""Local settings for the MadenGuard backend foundation.

The first backend version is intentionally JSON-backed. It gives the team
stable API contracts before we add database models or heavier ML services.
"""

from __future__ import annotations

from pathlib import Path
import os


BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent


def csv_env(name: str, default: str) -> list[str]:
    value = os.environ.get(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "local-dev-only-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() in {"1", "true", "yes", "on"}
ALLOWED_HOSTS = csv_env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,0.0.0.0,testserver")

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "apps.api",
    "apps.common",
    "apps.lidar",
    "apps.sensors",
    "apps.workers",
    "apps.risk",
    "apps.routing",
    "apps.scenarios",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "apps.common.middleware.SimpleCorsMiddleware",
]

ROOT_URLCONF = "madenguard_backend.urls"
WSGI_APPLICATION = "madenguard_backend.wsgi.application"
ASGI_APPLICATION = "madenguard_backend.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

LANGUAGE_CODE = "tr-tr"
TIME_ZONE = "Europe/Istanbul"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

MADENGUARD_DATA_ROOT = Path(
    os.environ.get("MADENGUARD_DATA_ROOT", BASE_DIR / "data_processed" / "sample")
).expanduser()
if not MADENGUARD_DATA_ROOT.is_absolute():
    MADENGUARD_DATA_ROOT = (BASE_DIR / MADENGUARD_DATA_ROOT).resolve()

MADENGUARD_CORS_ORIGINS = csv_env(
    "MADENGUARD_CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000",
)

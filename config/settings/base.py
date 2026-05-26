"""
config/settings/base.py
========================
Shared settings for all environments.
"""

from pathlib import Path
import environ

# Build paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# django-environ: read from .env file at project root
env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

# ──────────────────────────────────────────────────────────────────────────────
# Security
# ──────────────────────────────────────────────────────────────────────────────
SECRET_KEY = env("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

# ──────────────────────────────────────────────────────────────────────────────
# Application definition
# ──────────────────────────────────────────────────────────────────────────────
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "corsheaders",
    "django_celery_results",
    "django_celery_beat",
]

LOCAL_APPS = [
    "apps.seo_checker",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS":    [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ──────────────────────────────────────────────────────────────────────────────
# Database — PostgreSQL
# ──────────────────────────────────────────────────────────────────────────────
DATABASES = {
    "default": env.db("DATABASE_URL", default="postgres://postgres:postgres@localhost:5432/website_booster")
}

# ──────────────────────────────────────────────────────────────────────────────
# Celery
# ──────────────────────────────────────────────────────────────────────────────
CELERY_BROKER_URL            = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND        = "django-db"   # via django-celery-results
CELERY_CACHE_BACKEND         = "django-cache"
CELERY_ACCEPT_CONTENT        = ["json"]
CELERY_TASK_SERIALIZER       = "json"
CELERY_RESULT_SERIALIZER     = "json"
CELERY_TIMEZONE              = "Asia/Karachi"
CELERY_TASK_TRACK_STARTED    = True
CELERY_TASK_TIME_LIMIT       = 600   # 10 min hard limit per task

CELERY_TASK_ROUTES = {
    "seo_checker.run_seo_check": {"queue": "seo_checks"},
}

# ──────────────────────────────────────────────────────────────────────────────
# Django REST Framework
# ──────────────────────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        # SEO check endpoint: max 10 checks per hour per IP
        "seo_check": "10/hour",
    },
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
}

# ──────────────────────────────────────────────────────────────────────────────
# Third-party API keys (injected via .env)
# ──────────────────────────────────────────────────────────────────────────────
OPENAI_API_KEY           = env("OPENAI_API_KEY",           default="")
GOOGLE_PAGESPEED_API_KEY = env("GOOGLE_PAGESPEED_API_KEY", default="")

# ──────────────────────────────────────────────────────────────────────────────
# Internationalisation
# ──────────────────────────────────────────────────────────────────────────────
LANGUAGE_CODE = "en-us"
TIME_ZONE     = "Asia/Karachi"
USE_I18N      = True
USE_TZ        = True

# ──────────────────────────────────────────────────────────────────────────────
# Static & Media
# ──────────────────────────────────────────────────────────────────────────────
STATIC_URL  = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL  = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ──────────────────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style":  "{",
        },
    },
    "handlers": {
        "console": {
            "class":     "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level":    "INFO",
    },
    "loggers": {
        "django":        {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "apps":          {"handlers": ["console"], "level": "DEBUG",   "propagate": False},
        "celery":        {"handlers": ["console"], "level": "INFO",    "propagate": False},
    },
}

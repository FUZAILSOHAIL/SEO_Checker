"""Settings used only by pytest. The running app does not import this module."""
import os
import tempfile
from pathlib import Path

# Force test values before base.py reads the process environment or a
# developer .env, so local API keys and databases are never used.
os.environ["DJANGO_SECRET_KEY"] = "test-only-not-a-secret"
os.environ["DATABASE_URL"] = "sqlite:///unused-test-placeholder.sqlite3"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["ALLOWED_HOSTS"] = "localhost,127.0.0.1,testserver"
os.environ["OPENAI_API_KEY"] = ""
os.environ["GOOGLE_PAGESPEED_API_KEY"] = ""

from .base import *  # noqa: E402,F403

DEBUG = False
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]
# WhiteNoise warns when STATIC_ROOT is missing. Keep the directory out of the repo.
STATIC_ROOT = Path(tempfile.mkdtemp(prefix="seo-checker-static-"))

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "seo-checker-tests",
    }
}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# If a test forgets to mock the Celery call, run it in-process so the
# socket block fails the test instead of hanging on Redis.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

OPENAI_API_KEY = ""
GOOGLE_PAGESPEED_API_KEY = ""

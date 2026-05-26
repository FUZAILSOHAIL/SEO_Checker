from .base import *  # noqa

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]

# Use ngrok URL in dev for Shopify OAuth callbacks + webhooks
APP_BASE_URL = env("APP_BASE_URL", default="https://your-ngrok-id.ngrok.io")

# Allow all CORS in dev
CORS_ALLOW_ALL_ORIGINS = True

# Disable password validators in dev
AUTH_PASSWORD_VALIDATORS = []

# django-debug-toolbar (install separately if needed)
INSTALLED_APPS += ["django_extensions"]  # noqa

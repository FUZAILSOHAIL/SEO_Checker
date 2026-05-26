from .base import *  # noqa

DEBUG = False

# HTTPS / security hardening
SECURE_SSL_REDIRECT             = True
SECURE_HSTS_SECONDS             = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS  = True
SECURE_HSTS_PRELOAD             = True
SESSION_COOKIE_SECURE           = True
CSRF_COOKIE_SECURE              = True

# Content Security Policy — tighten as needed
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# CORS: restrict to your front-end domain(s)
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])

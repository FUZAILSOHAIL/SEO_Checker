"""
config/celery.py — Celery application bootstrap
"""

import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery("website_booster")

# Pull all Celery config from Django settings under the CELERY_ namespace
app.config_from_object("django.conf:settings", namespace="CELERY")

# Silence the Celery 6.0 deprecation warning
app.conf.broker_connection_retry_on_startup = True

# Auto-discover tasks in every installed app
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")

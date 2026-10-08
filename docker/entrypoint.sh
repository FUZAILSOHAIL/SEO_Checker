#!/bin/sh
# Container entrypoint. Migrations run only for the web service
# (RUN_MIGRATIONS=1) so the Celery process does not race SQLite.
set -eu

if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
    python manage.py migrate --noinput
    python manage.py collectstatic --noinput
fi

exec "$@"

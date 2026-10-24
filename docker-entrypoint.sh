#!/bin/sh
set -eu

if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
  alembic -c /app/backend/alembic.ini upgrade head
fi

if [ "${INIT_STORAGE:-0}" = "1" ]; then
  python /app/backend/scripts/init_storage.py
fi

if [ "${SEED_DATA:-0}" = "1" ]; then
  python /app/backend/scripts/seed_data_admin.py
fi

exec "$@"

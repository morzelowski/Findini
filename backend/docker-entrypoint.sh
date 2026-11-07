#!/bin/sh
set -e
# Migracje są idempotentne — bezpieczne przy każdym starcie.
alembic upgrade head
if [ "${FINDINI_SEED_DEMO:-0}" = "1" ]; then
  python -m scripts.seed_demo --if-empty
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers "${FINDINI_WORKERS:-1}" --proxy-headers --forwarded-allow-ips="${FINDINI_FORWARDED_ALLOW_IPS:-127.0.0.1}" --no-server-header

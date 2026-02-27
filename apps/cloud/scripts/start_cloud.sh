#!/usr/bin/env sh
set -eu

MAX_ATTEMPTS="${DB_WAIT_MAX_ATTEMPTS:-40}"
SLEEP_SECONDS="${DB_WAIT_SLEEP_SECONDS:-2}"
ATTEMPT=1

detect_bind_host() {
  if [ -n "${CLOUD_BIND_HOST:-}" ]; then
    printf "%s" "${CLOUD_BIND_HOST}"
    return
  fi

  # Container runtime needs external bind for service networking.
  if [ -f "/.dockerenv" ] || [ "${CONTAINER_RUNTIME:-0}" = "1" ]; then
    printf "0.0.0.0"
    return
  fi

  # Local non-container runs should default to loopback.
  printf "127.0.0.1"
}

HOST="$(detect_bind_host)"

until python - <<'PY'
import os
from sqlalchemy import create_engine, text

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
with engine.connect() as conn:
    conn.execute(text("SELECT 1"))
PY
do
  if [ "$ATTEMPT" -ge "$MAX_ATTEMPTS" ]; then
    echo "Database readiness check failed after ${MAX_ATTEMPTS} attempts" >&2
    exit 1
  fi
  echo "Waiting for database... attempt ${ATTEMPT}/${MAX_ATTEMPTS}"
  ATTEMPT=$((ATTEMPT + 1))
  sleep "$SLEEP_SECONDS"
done

alembic upgrade head
exec python -m uvicorn main:app --host "${HOST}" --port 8000

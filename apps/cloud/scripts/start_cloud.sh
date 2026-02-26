#!/usr/bin/env sh
set -eu

MAX_ATTEMPTS="${DB_WAIT_MAX_ATTEMPTS:-40}"
SLEEP_SECONDS="${DB_WAIT_SLEEP_SECONDS:-2}"
HOST="${CLOUD_BIND_HOST:-0.0.0.0}"
ATTEMPT=1

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

#!/usr/bin/env bash
set -euo pipefail

# Bundled Edge launcher for distribution builds.
# Uses bundled Python runtime + venv and never depends on Poetry.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="${SCRIPT_DIR}/pyvenv/bin/python"
APP_SRC_DIR="${SCRIPT_DIR}/app"

PORT="${EDGE_PORT:-${1:-8787}}"
TOKEN="${EDGE_AUTH_TOKEN:-${2:-dev-token}}"
ENV_NAME="${EDGE_ENV:-${3:-prod}}"
HOST="127.0.0.1"

if [[ ! -x "${VENV_PYTHON}" ]]; then
  echo "Bundled edge python not found at ${VENV_PYTHON}" >&2
  exit 1
fi

export EDGE_PORT="${PORT}"
export EDGE_HOST="${HOST}"
export EDGE_AUTH_TOKEN="${TOKEN}"
export EDGE_ENV="${ENV_NAME}"

# If bundled source is present, prepend it as a runtime fallback.
if [[ -d "${APP_SRC_DIR}" ]]; then
  if [[ -n "${PYTHONPATH:-}" ]]; then
    export PYTHONPATH="${APP_SRC_DIR}:${PYTHONPATH}"
  else
    export PYTHONPATH="${APP_SRC_DIR}"
  fi
fi

exec "${VENV_PYTHON}" -m uvicorn sentinelid_edge.main:app \
  --host "${HOST}" \
  --port "${PORT}" \
  --no-access-log \
  --log-level info

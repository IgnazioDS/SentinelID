#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
EDGE_DIR="${REPO_ROOT}/apps/edge"

"${REPO_ROOT}/scripts/dev/edge_env.sh" preflight

if command -v poetry >/dev/null 2>&1; then
  POETRY_BIN="$(command -v poetry)"
elif [[ -x "${EDGE_DIR}/.venv/bin/poetry" ]]; then
  POETRY_BIN="${EDGE_DIR}/.venv/bin/poetry"
else
  echo "error: Poetry not found. Install Poetry or create ${EDGE_DIR}/.venv with Poetry." >&2
  exit 1
fi

cd "${EDGE_DIR}"
exec "${POETRY_BIN}" run python -m sentinelid_edge.services.telemetry.preflight

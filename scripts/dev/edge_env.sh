#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
EDGE_DIR="${REPO_ROOT}/apps/edge"

resolve_poetry() {
  if command -v poetry >/dev/null 2>&1; then
    command -v poetry
    return 0
  fi
  if [[ -x "${EDGE_DIR}/.venv/bin/poetry" ]]; then
    echo "${EDGE_DIR}/.venv/bin/poetry"
    return 0
  fi
  return 1
}

warn_active_venv() {
  if [[ -n "${VIRTUAL_ENV:-}" && "${VIRTUAL_ENV}" != "${EDGE_DIR}/.venv" ]]; then
    echo "warning: active virtualenv detected at ${VIRTUAL_ENV}" >&2
    echo "warning: SentinelID edge uses Poetry-managed env; avoid activating unrelated venvs before running make targets" >&2
  fi
}

run_preflight() {
  warn_active_venv

  local poetry_bin
  if ! poetry_bin="$(resolve_poetry)"; then
    echo "error: Poetry not found. Install Poetry or create ${EDGE_DIR}/.venv with Poetry." >&2
    exit 1
  fi

  cd "${EDGE_DIR}"
  if ! "${poetry_bin}" run python - <<'PY' >/dev/null 2>&1
import pydantic_settings  # noqa: F401
import uvicorn  # noqa: F401
PY
  then
    echo "error: edge dependency preflight failed (missing pydantic_settings/uvicorn in Poetry env)." >&2
    echo "run: cd apps/edge && poetry install" >&2
    exit 1
  fi
}

run_edge() {
  run_preflight

  local poetry_bin
  poetry_bin="$(resolve_poetry)"

  cd "${EDGE_DIR}"
  exec "${poetry_bin}" run python -m uvicorn sentinelid_edge.main:app \
    --host "${EDGE_HOST:-127.0.0.1}" \
    --port "${EDGE_PORT:-8787}"
}

open_edge_shell() {
  run_preflight

  local poetry_bin
  poetry_bin="$(resolve_poetry)"

  cd "${EDGE_DIR}"
  exec "${poetry_bin}" run "${SHELL:-/bin/bash}"
}

MODE="${1:-preflight}"
case "${MODE}" in
  preflight)
    run_preflight
    ;;
  run)
    run_edge
    ;;
  shell)
    open_edge_shell
    ;;
  *)
    echo "usage: $0 [preflight|run|shell]" >&2
    exit 2
    ;;
esac

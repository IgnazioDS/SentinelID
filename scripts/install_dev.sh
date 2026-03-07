#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

install_edge() {
  cd "${ROOT_DIR}/apps/edge"
  export POETRY_VIRTUALENVS_IN_PROJECT=1
  if command -v poetry >/dev/null 2>&1; then
    poetry install --no-interaction
    return
  fi
  if [[ -x .venv/bin/poetry ]]; then
    .venv/bin/poetry install --no-interaction
    return
  fi
  echo "Poetry is required for apps/edge. Install Poetry before running make install-dev."
  exit 1
}

install_node_app() {
  local app_dir="$1"
  cd "${ROOT_DIR}/${app_dir}"
  npm ci --no-audit --no-fund
}

echo "[install-dev] edge dependencies"
install_edge

echo "[install-dev] desktop dependencies"
install_node_app "apps/desktop"

echo "[install-dev] admin dependencies"
install_node_app "apps/admin"

echo "[install-dev] completed"

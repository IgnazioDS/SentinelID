#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DESKTOP_APP="${PROJECT_ROOT}/apps/desktop"
RESOURCES_DIR="${DESKTOP_APP}/resources/edge"
VENV_DIR="${RESOURCES_DIR}/pyvenv"

echo "Smoke testing desktop bundling artifacts"

if [[ ! -d "${VENV_DIR}" ]]; then
  echo "Bundled venv not found at ${VENV_DIR}. Run ./scripts/bundle_edge_venv.sh first."
  exit 1
fi

if [[ ! -f "${VENV_DIR}/bin/python" ]]; then
  echo "Python executable missing in bundled venv"
  exit 1
fi

if ! "${VENV_DIR}/bin/python" -m uvicorn --version >/dev/null 2>&1; then
  echo "uvicorn missing in bundled venv"
  exit 1
fi

if [[ ! -x "${RESOURCES_DIR}/run_edge.sh" ]]; then
  echo "run_edge.sh missing or not executable at ${RESOURCES_DIR}/run_edge.sh"
  exit 1
fi

if ! grep -q '"resources"' "${DESKTOP_APP}/src-tauri/tauri.conf.json"; then
  echo "tauri.conf.json is missing resources configuration"
  exit 1
fi

for pkg in fastapi uvicorn pydantic sqlalchemy; do
  if ! "${VENV_DIR}/bin/python" -m pip show "${pkg}" >/dev/null 2>&1; then
    echo "Required package ${pkg} missing in bundled venv"
    exit 1
  fi
done

VENV_SIZE_KB="$(du -s "${VENV_DIR}" | awk '{print $1}')"
if [[ "${VENV_SIZE_KB}" -lt 50000 ]]; then
  echo "Bundled venv too small (${VENV_SIZE_KB}KB): expected >50000KB"
  exit 1
fi
if [[ "${VENV_SIZE_KB}" -gt 2000000 ]]; then
  echo "Bundled venv too large (${VENV_SIZE_KB}KB): expected <2000000KB"
  exit 1
fi

bash -n "${RESOURCES_DIR}/run_edge.sh"

echo "Bundling smoke test passed"

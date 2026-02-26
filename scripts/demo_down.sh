#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

if [[ "${1:-}" == "--volumes" ]]; then
  echo "[demo-down] stopping demo stack and removing volumes"
  docker compose down -v
else
  echo "[demo-down] stopping demo stack"
  docker compose down
fi

#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=scripts/lib/compose_env_file.sh
source "${SCRIPT_DIR}/lib/compose_env_file.sh"

cd "${REPO_ROOT}"
prepare_compose_env_file "${REPO_ROOT}"

if [[ "${1:-}" == "--volumes" ]]; then
  echo "[demo-down] stopping demo stack and removing volumes"
  compose_cmd down -v
else
  echo "[demo-down] stopping demo stack"
  compose_cmd down
fi

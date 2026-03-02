#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=scripts/lib/compose_env_file.sh
source "${SCRIPT_DIR}/lib/compose_env_file.sh"

cd "${REPO_ROOT}"
prepare_compose_env_file "${REPO_ROOT}"

attempt=1
pull_flag=""
if [[ "${DOCKER_BUILD_PULL:-0}" == "1" ]]; then
  pull_flag="--pull"
fi

until compose_cmd build ${pull_flag} cloud admin; do
  if [[ "${attempt}" -ge 3 ]]; then
    echo "docker compose build failed after ${attempt} attempts"
    exit 1
  fi
  echo "docker compose build failed (attempt ${attempt}), retrying..."
  attempt=$((attempt + 1))
  sleep 2
done

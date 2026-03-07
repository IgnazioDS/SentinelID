#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CURRENT_REF="$(git -C "${ROOT_DIR}" rev-parse --abbrev-ref HEAD)"
TMP_DIR="$(mktemp -d -t sentinelid_fresh_clone.XXXXXX)"
CLONE_DIR="${TMP_DIR}/SentinelID"
DRY_RUN=0
RUN_INTERACTIVE_DEMO="${RUN_INTERACTIVE_DEMO:-0}"
DEMO_AUTO_CLOSE_SECONDS="${DEMO_AUTO_CLOSE_SECONDS:-20}"

if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
fi

cleanup() {
  if [[ -d "${CLONE_DIR}" ]]; then
    (cd "${CLONE_DIR}" && make demo-down >/dev/null 2>&1) || true
  fi
  rm -rf "${TMP_DIR}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

run_clone_cmd() {
  local description="$1"
  shift
  echo "[fresh-clone] ${description}"
  if [[ "${DRY_RUN}" == "1" ]]; then
    printf '  %q' "$@"
    printf '\n'
    return 0
  fi
  "$@"
}

SANITIZED_ENV=(
  "PATH=${PATH}"
  "HOME=${HOME}"
  "TERM=${TERM:-dumb}"
  "SHELL=${SHELL:-/bin/sh}"
)

run_in_clone() {
  local description="$1"
  shift
  run_clone_cmd "${description}" env -i "${SANITIZED_ENV[@]}" "$@"
}

if ! command -v rsync >/dev/null 2>&1; then
  echo "rsync is required for scripts/check_fresh_clone_bootstrap.sh"
  exit 1
fi

mkdir -p "${CLONE_DIR}"
run_clone_cmd "stage current working tree snapshot from ${CURRENT_REF}" \
  rsync -a --delete \
    --exclude ".git/" \
    --exclude "apps/edge/.venv/" \
    --exclude "apps/cloud/.venv/" \
    --exclude "apps/desktop/node_modules/" \
    --exclude "apps/admin/node_modules/" \
    --exclude "apps/desktop/src-tauri/target/" \
    --exclude "apps/desktop/dist/" \
    --exclude "output/" \
    --exclude "__pycache__/" \
    "${ROOT_DIR}/" "${CLONE_DIR}/"
run_clone_cmd "copy .env.example to .env" cp "${CLONE_DIR}/.env.example" "${CLONE_DIR}/.env"
run_in_clone "install lockfile-managed dev dependencies" make -C "${CLONE_DIR}" install-dev
run_in_clone "start demo stack" make -C "${CLONE_DIR}" demo-up
run_in_clone "verify beginner path non-interactively" make -C "${CLONE_DIR}" demo-verify

if [[ "${RUN_INTERACTIVE_DEMO}" == "1" ]]; then
  run_in_clone "launch demo desktop with auto-close" env DEMO_AUTO_CLOSE_SECONDS="${DEMO_AUTO_CLOSE_SECONDS}" make -C "${CLONE_DIR}" demo
fi

run_in_clone "stop demo stack" make -C "${CLONE_DIR}" demo-down

echo "[fresh-clone] bootstrap check passed"

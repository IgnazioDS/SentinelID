#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DESKTOP_DIR="${ROOT_DIR}/apps/desktop"

cd "${DESKTOP_DIR}"

if [[ ! -d node_modules ]]; then
  npm ci
fi

if [[ ! -d "${DESKTOP_DIR}/dist" ]]; then
  npm run build >/dev/null
fi

TARGET_DIR="${DESKTOP_DIR}/dist"
if [[ ! -d "${TARGET_DIR}" ]]; then
  echo "Desktop static build output not found at ${TARGET_DIR}"
  exit 1
fi

patterns=(
  "VITE_ADMIN_TOKEN"
  "ADMIN_API_TOKEN"
  "dev-admin-token"
  "X-Admin-Token"
)

if [[ -n "${ADMIN_API_TOKEN:-}" ]]; then
  patterns+=("${ADMIN_API_TOKEN}")
fi

for pattern in "${patterns[@]}"; do
  if rg -a -n --fixed-strings "${pattern}" "${TARGET_DIR}" >/dev/null 2>&1; then
    echo "Found forbidden admin token pattern in desktop bundle: ${pattern}"
    exit 1
  fi
done

echo "Desktop bundle token exposure check passed"

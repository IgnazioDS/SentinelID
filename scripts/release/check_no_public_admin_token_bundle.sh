#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ADMIN_DIR="${ROOT_DIR}/apps/admin"

cd "${ADMIN_DIR}"

if [[ ! -d node_modules ]]; then
  npm ci
fi

npm run build >/dev/null

TARGET_DIR="${ADMIN_DIR}/.next/static"
if [[ ! -d "${TARGET_DIR}" ]]; then
  echo "Admin static build output not found at ${TARGET_DIR}"
  exit 1
fi

patterns=(
  "NEXT_PUBLIC_ADMIN_TOKEN"
  "dev-admin-token"
)

if [[ -n "${ADMIN_API_TOKEN:-}" ]]; then
  patterns+=("${ADMIN_API_TOKEN}")
fi

for pattern in "${patterns[@]}"; do
  if rg -a -n --fixed-strings "${pattern}" "${TARGET_DIR}" >/dev/null 2>&1; then
    echo "Found forbidden admin token pattern in client bundle: ${pattern}"
    exit 1
  fi
done

echo "Client bundle token exposure check passed"

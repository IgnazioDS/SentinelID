#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
OPENAPI_DIR="${REPO_ROOT}/packages/shared-contracts/openapi"
TS_DIR="${REPO_ROOT}/packages/shared-contracts/ts"

EDGE_SPEC="${OPENAPI_DIR}/edge.openapi.yaml"
CLOUD_SPEC="${OPENAPI_DIR}/cloud.openapi.yaml"
EDGE_OUT="${TS_DIR}/edge.ts"
CLOUD_OUT="${TS_DIR}/cloud.ts"
INDEX_OUT="${TS_DIR}/index.ts"

if ! command -v npx >/dev/null 2>&1; then
  echo "error: npx is required to generate OpenAPI TypeScript types." >&2
  exit 1
fi

for spec in "${EDGE_SPEC}" "${CLOUD_SPEC}"; do
  if [[ ! -f "${spec}" ]]; then
    echo "error: missing OpenAPI spec: ${spec}" >&2
    exit 1
  fi
done

mkdir -p "${TS_DIR}"

echo "[gen-types] generating edge contract types"
npx --yes openapi-typescript "${EDGE_SPEC}" --output "${EDGE_OUT}"

echo "[gen-types] generating cloud contract types"
npx --yes openapi-typescript "${CLOUD_SPEC}" --output "${CLOUD_OUT}"

cat > "${INDEX_OUT}" <<'EOF'
export type {
  paths as EdgePaths,
  components as EdgeComponents,
  operations as EdgeOperations,
} from "./edge";
export type {
  paths as CloudPaths,
  components as CloudComponents,
  operations as CloudOperations,
} from "./cloud";
EOF

echo "[gen-types] wrote:"
echo "  - ${EDGE_OUT}"
echo "  - ${CLOUD_OUT}"
echo "  - ${INDEX_OUT}"

#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

"${REPO_ROOT}/scripts/bundle_edge_venv.sh"

pushd "${REPO_ROOT}/apps/desktop" >/dev/null
npm run tauri build
popd >/dev/null

"${REPO_ROOT}/scripts/smoke_test_bundling.sh"
"${REPO_ROOT}/scripts/smoke_test_desktop.sh"

echo "Desktop bundle build + smoke validation complete"


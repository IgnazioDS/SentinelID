#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <data/genuine_dir> <data/impostor_dir> [target_far]"
  exit 1
fi

GENUINE_DIR="$1"
IMPOSTOR_DIR="$2"
TARGET_FAR="${3:-0.01}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
OUT_DIR="${SCRIPT_DIR}/out"
mkdir -p "${OUT_DIR}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_FILE="${OUT_DIR}/calibration_${STAMP}.json"

EDGE_VENV_PYTHON="${REPO_ROOT}/apps/edge/.venv/bin/python"
if [[ -x "${EDGE_VENV_PYTHON}" ]]; then
  PYTHON_BIN="${EDGE_VENV_PYTHON}"
else
  PYTHON_BIN="python3"
fi

"${PYTHON_BIN}" - "${REPO_ROOT}" "${GENUINE_DIR}" "${IMPOSTOR_DIR}" "${TARGET_FAR}" "${OUT_FILE}" <<'PY'
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

repo_root = Path(sys.argv[1])
genuine_dir = sys.argv[2]
impostor_dir = sys.argv[3]
target_far = float(sys.argv[4])
out_file = Path(sys.argv[5])

sys.path.insert(0, str(repo_root / "apps" / "edge"))

from sentinelid_edge.services.vision.calibration import run_threshold_calibration

report = run_threshold_calibration(
    genuine_dir=genuine_dir,
    impostor_dir=impostor_dir,
    target_far=target_far,
)

output = {
    "eval_version": "v1.2.0",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "dataset": {
        "genuine_dir": genuine_dir,
        "impostor_dir": impostor_dir,
    },
    "target_far": target_far,
    "sanitized": True,
    "report": report,
}
out_file.write_text(json.dumps(output, indent=2), encoding="utf-8")
print(str(out_file))
PY

printf 'Wrote calibration report: %s\n' "${OUT_FILE}"

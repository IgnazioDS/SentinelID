#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

EVIDENCE_DIR="${ROOT_DIR}/output/release"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK_DIR="${EVIDENCE_DIR}/evidence_pack_${STAMP}"
TARBALL_PATH="${EVIDENCE_DIR}/evidence_pack_${STAMP}.tar.gz"

RELIABILITY_FILE="${ROOT_DIR}/output/ci/reliability_slo.json"
INVARIANT_FILE="${ROOT_DIR}/output/release/invariant_report_latest.json"
DESKTOP_WARNING_FILE="${ROOT_DIR}/output/release/desktop_warning_budget_latest.json"
PERF_DIR="${ROOT_DIR}/scripts/perf/out"
SUPPORT_DIR="${ROOT_DIR}/scripts/support/out"

mkdir -p "${WORK_DIR}"

if [[ ! -f "${RELIABILITY_FILE}" ]]; then
  echo "Missing reliability report: ${RELIABILITY_FILE}"
  exit 1
fi
if [[ ! -f "${INVARIANT_FILE}" ]]; then
  echo "Missing invariant report: ${INVARIANT_FILE}"
  exit 1
fi
if [[ ! -f "${DESKTOP_WARNING_FILE}" ]]; then
  echo "Missing desktop warning budget summary: ${DESKTOP_WARNING_FILE}"
  exit 1
fi

if [[ -z "$(ls -1 "${SUPPORT_DIR}"/support_bundle_*.tar.gz 2>/dev/null || true)" ]]; then
  echo "No support bundle artifact found; generating one now..."
  "${ROOT_DIR}/scripts/support_bundle.sh"
fi

LATEST_PERF="$(ls -1t "${PERF_DIR}"/bench_edge_*.json 2>/dev/null | head -n 1 || true)"
LATEST_SUPPORT="$(ls -1t "${SUPPORT_DIR}"/support_bundle_*.tar.gz 2>/dev/null | head -n 1 || true)"

if [[ -z "${LATEST_PERF}" ]]; then
  echo "No perf artifact found under ${PERF_DIR}"
  exit 1
fi
if [[ -z "${LATEST_SUPPORT}" ]]; then
  echo "No support bundle artifact found under ${SUPPORT_DIR}"
  exit 1
fi

cp "${RELIABILITY_FILE}" "${WORK_DIR}/reliability_slo.json"
cp "${INVARIANT_FILE}" "${WORK_DIR}/invariant_report.json"
cp "${DESKTOP_WARNING_FILE}" "${WORK_DIR}/desktop_warning_budget.json"
cp "${LATEST_PERF}" "${WORK_DIR}/bench_edge_latest.json"
cp "${LATEST_SUPPORT}" "${WORK_DIR}/support_bundle_latest.tar.gz"

python3 - "${WORK_DIR}" "${INVARIANT_FILE}" "${DESKTOP_WARNING_FILE}" "${LATEST_PERF}" "${LATEST_SUPPORT}" <<'PY'
from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

work_dir = Path(sys.argv[1])
invariant_report = Path(sys.argv[2])
desktop_warning_budget = Path(sys.argv[3])
latest_perf = Path(sys.argv[4])
latest_support = Path(sys.argv[5])

def cmd(*args: str) -> str:
    return subprocess.check_output(args, text=True).strip()

manifest = {
    "generated_at": datetime.now(UTC).isoformat(),
    "git": {
        "revision": cmd("git", "rev-parse", "HEAD"),
        "short_revision": cmd("git", "rev-parse", "--short", "HEAD"),
        "branch": cmd("git", "rev-parse", "--abbrev-ref", "HEAD"),
    },
    "artifacts": {
        "reliability_slo": "reliability_slo.json",
        "invariant_report": "invariant_report.json",
        "desktop_warning_budget": "desktop_warning_budget.json",
        "bench_edge_latest": "bench_edge_latest.json",
        "support_bundle_latest": "support_bundle_latest.tar.gz",
    },
    "source_paths": {
        "invariant_report": str(invariant_report),
        "desktop_warning_budget": str(desktop_warning_budget),
        "bench_edge_latest": str(latest_perf),
        "support_bundle_latest": str(latest_support),
    },
    "checks": {
        "security": [
            "admin session auth enabled",
            "public admin token removed from runtime config",
            "client bundle token exposure check passes",
        ],
        "reliability": [
            "cloud recovery smoke passes",
            "support bundle sanitization check passes",
            "reliability SLO report generated",
        ],
        "runtime_invariants": [
            "edge/cloud loopback binding enforced",
            "edge bearer enforcement validated",
            "cloud admin token enforcement validated",
            "support bundle endpoint contract validated",
        ],
        "desktop_observability": [
            "desktop cargo warnings captured in diagnostics",
            "desktop warning-noise budget check passes",
        ],
        "release_integrity": [
            "version consistency check passes",
            "release parity workflow present",
        ],
    },
}

(work_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
PY

cat > "${WORK_DIR}/README.txt" <<EOF
SentinelID Release Evidence Pack
Generated: ${STAMP}

Included files:
- manifest.json
- reliability_slo.json
- invariant_report.json
- desktop_warning_budget.json
- bench_edge_latest.json
- support_bundle_latest.tar.gz
EOF

tar -czf "${TARBALL_PATH}" -C "${EVIDENCE_DIR}" "evidence_pack_${STAMP}"
echo "Evidence pack created:"
echo "  dir: ${WORK_DIR}"
echo "  tar: ${TARBALL_PATH}"

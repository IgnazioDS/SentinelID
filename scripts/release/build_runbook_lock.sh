#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

EVIDENCE_DIR="${ROOT_DIR}/output/release"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

LOCK_LABEL="${RUNBOOK_LOCK_LABEL:-}"
if [[ -z "${LOCK_LABEL}" ]]; then
  if git describe --tags --exact-match >/dev/null 2>&1; then
    LOCK_LABEL="$(git describe --tags --exact-match)"
  else
    LOCK_LABEL="$(git rev-parse --short HEAD)"
  fi
fi

SANITIZED_LABEL="$(echo "${LOCK_LABEL}" | tr '/ ' '__' | tr -cd '[:alnum:]._-')"
if [[ -z "${SANITIZED_LABEL}" ]]; then
  SANITIZED_LABEL="unknown"
fi

WORK_DIR="${EVIDENCE_DIR}/runbook_lock_${SANITIZED_LABEL}_${STAMP}"
TARBALL_PATH="${EVIDENCE_DIR}/runbook_lock_${SANITIZED_LABEL}.tar.gz"

mkdir -p "${WORK_DIR}/docs"

cp "${ROOT_DIR}/RUNBOOK.md" "${WORK_DIR}/docs/RUNBOOK.md"
cp "${ROOT_DIR}/docs/RELEASE.md" "${WORK_DIR}/docs/RELEASE.md"
cp "${ROOT_DIR}/docs/DEMO_CHECKLIST.md" "${WORK_DIR}/docs/DEMO_CHECKLIST.md"
cp "${ROOT_DIR}/docs/RECOVERY.md" "${WORK_DIR}/docs/RECOVERY.md"
cp "${ROOT_DIR}/docs/PILOT_FREEZE.md" "${WORK_DIR}/docs/PILOT_FREEZE.md"
cp "${ROOT_DIR}/CHANGELOG.md" "${WORK_DIR}/docs/CHANGELOG.md"

python3 - "${WORK_DIR}" "${LOCK_LABEL}" "${TARBALL_PATH}" <<'PY'
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

work_dir = Path(sys.argv[1])
lock_label = sys.argv[2]
tarball_path = sys.argv[3]
docs_dir = work_dir / "docs"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


checksums: dict[str, str] = {}
files: list[str] = []
for doc in sorted(docs_dir.glob("*.md")):
    rel = doc.relative_to(work_dir).as_posix()
    digest = hashlib.sha256(doc.read_bytes()).hexdigest()
    checksums[rel] = digest
    files.append(rel)

sha_lines = [f"{checksums[path]}  {path}" for path in files]
(work_dir / "SHA256SUMS").write_text("\n".join(sha_lines) + "\n", encoding="utf-8")

manifest = {
    "generated_at": datetime.now(UTC).isoformat(),
    "lock_label": lock_label,
    "git": {
        "revision": git("rev-parse", "HEAD"),
        "short_revision": git("rev-parse", "--short", "HEAD"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
    },
    "files": files,
    "checksums_sha256": checksums,
    "output_tarball": tarball_path,
}

(work_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
PY

cat > "${WORK_DIR}/README.txt" <<EOF
SentinelID Known-Good Runbook Lock
Generated: ${STAMP}
Label: ${LOCK_LABEL}

Included files:
- manifest.json
- SHA256SUMS
- docs/RUNBOOK.md
- docs/RELEASE.md
- docs/DEMO_CHECKLIST.md
- docs/RECOVERY.md
- docs/PILOT_FREEZE.md
- docs/CHANGELOG.md
EOF

tar -czf "${TARBALL_PATH}" -C "${EVIDENCE_DIR}" "$(basename "${WORK_DIR}")"

echo "Runbook lock artifact created:"
for artifact in "${WORK_DIR}" "${TARBALL_PATH}"; do
  echo "  ${artifact}"
done

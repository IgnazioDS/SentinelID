#!/usr/bin/env bash
set -euo pipefail

CLOUD_URL="${CLOUD_URL:-http://127.0.0.1:8000}"
ADMIN_TOKEN="${ADMIN_TOKEN:-${ADMIN_API_TOKEN:-}}"
WINDOW="${WINDOW:-24h}"
EVENTS_LIMIT="${EVENTS_LIMIT:-50}"

if [[ -z "${ADMIN_TOKEN}" ]]; then
  echo "ADMIN_TOKEN (or ADMIN_API_TOKEN) is required"
  exit 1
fi

tmp_bundle="$(mktemp -t sentinelid_support_bundle.XXXXXX.tar.gz)"
trap 'rm -f "${tmp_bundle}"' EXIT

curl -fsS -H "X-Admin-Token: ${ADMIN_TOKEN}" -X POST \
  "${CLOUD_URL}/v1/admin/support-bundle?window=${WINDOW}&events_limit=${EVENTS_LIMIT}" \
  -o "${tmp_bundle}"

python3 - "${tmp_bundle}" <<'PY'
from __future__ import annotations

import json
import tarfile
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.exists() or path.stat().st_size == 0:
    raise SystemExit("support bundle download is empty")

forbidden_fragments = ("token", "signature", "embedding", "frame", "image")
allowed_redacted = {"[REDACTED]", "", None}
violations = []

def inspect(value, ctx: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            lower = str(key).lower()
            if any(fragment in lower for fragment in forbidden_fragments):
                if isinstance(child, (dict, list)) and child not in ({}, []):
                    violations.append(f"{ctx}.{key} non-empty structured sensitive field")
                elif child not in allowed_redacted:
                    violations.append(f"{ctx}.{key}={child!r}")
            inspect(child, f"{ctx}.{key}")
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            inspect(child, f"{ctx}[{idx}]")
    elif isinstance(value, str):
        lower = value.lower()
        if lower.startswith("bearer ") and value != "Bearer [REDACTED]":
            violations.append(f"{ctx} has non-redacted bearer token")
        if lower.startswith("data:image/"):
            violations.append(f"{ctx} has raw image data")

json_count = 0
with tarfile.open(path, mode="r:gz") as archive:
    members = [member for member in archive.getmembers() if member.isfile()]
    if not members:
        raise SystemExit("support bundle has no files")
    for member in members:
        if not member.name.endswith(".json"):
            continue
        payload = archive.extractfile(member)
        if payload is None:
            continue
        data = json.loads(payload.read().decode("utf-8"))
        inspect(data, member.name)
        json_count += 1

if json_count == 0:
    raise SystemExit("support bundle missing json payloads")
if violations:
    raise SystemExit("support bundle sanitization violations: " + "; ".join(violations[:8]))

print("support bundle sanitization check passed")
PY

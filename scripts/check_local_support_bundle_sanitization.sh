#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SUPPORT_OUT_DIR="${ROOT_DIR}/scripts/support/out"
BUNDLE_PATH="${BUNDLE_PATH:-}"

if [[ -z "${BUNDLE_PATH}" ]]; then
  BUNDLE_PATH="$(ls -1t "${SUPPORT_OUT_DIR}"/support_bundle_*.tar.gz 2>/dev/null | head -n 1 || true)"
fi

if [[ -z "${BUNDLE_PATH}" || ! -f "${BUNDLE_PATH}" ]]; then
  echo "Support bundle artifact not found. Set BUNDLE_PATH or run scripts/support_bundle.sh first."
  exit 1
fi

python3 - "${BUNDLE_PATH}" <<'PY'
from __future__ import annotations

import json
import os
import tarfile
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.exists() or path.stat().st_size == 0:
    raise SystemExit("support bundle artifact is empty")

forbidden_fragments = ("token", "signature", "embedding", "frame", "image")
allowed_redacted = {"[REDACTED]", "", None}
violations: list[str] = []

forbidden_literals = []
for key in ("EDGE_TOKEN", "EDGE_AUTH_TOKEN", "ADMIN_TOKEN", "ADMIN_API_TOKEN"):
    value = os.environ.get(key)
    if value:
        forbidden_literals.append(value)


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
        for literal in forbidden_literals:
            if literal in value:
                violations.append(f"{ctx} contains live credential value")
                break


json_count = 0
with tarfile.open(path, mode="r:gz") as archive:
    members = [member for member in archive.getmembers() if member.isfile()]
    if not members:
        raise SystemExit("support bundle has no files")

    for member in members:
        leaf = Path(member.name).name
        if leaf.startswith("._"):
            continue
        if not member.name.endswith(".json"):
            continue
        payload = archive.extractfile(member)
        if payload is None:
            continue
        try:
            data = json.loads(payload.read().decode("utf-8"))
        except Exception as exc:  # pragma: no cover
            violations.append(f"{member.name} invalid json: {exc}")
            continue
        inspect(data, member.name)
        json_count += 1

if json_count == 0:
    raise SystemExit("support bundle missing json payloads")
if violations:
    raise SystemExit("local support bundle sanitization violations: " + "; ".join(violations[:8]))

print(f"local support bundle sanitization check passed ({path})")
PY

#!/usr/bin/env bash
set -euo pipefail

matches="$(pgrep -fl "run_edge.sh|sentinelid_edge.main:app" || true)"

if [[ -n "${matches}" ]]; then
  echo "Found potential orphan edge process(es):"
  echo "${matches}"
  exit 1
fi

echo "No orphan edge processes detected"

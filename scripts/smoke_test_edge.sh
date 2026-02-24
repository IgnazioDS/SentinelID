#!/usr/bin/env bash
set -euo pipefail

EDGE_URL="${EDGE_URL:-http://127.0.0.1:8787}"
EDGE_TOKEN="${EDGE_TOKEN:-devtoken}"

echo "Running edge smoke test against ${EDGE_URL}"

python3 - "${EDGE_URL}" "${EDGE_TOKEN}" <<'PY'
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

edge_url = sys.argv[1].rstrip("/")
token = sys.argv[2]

FRAME_DATA_URL = (
    "data:image/jpeg;base64,"
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wCEAAkGBxISEhUTEhIVFhUXFRUVFRUVFRUVFRUXFhUX"
    "FhUVFRUYHSggGBolHRUVITEhJSkrLi4uFx8zODMsNygtLisBCgoKDg0OGhAQGi0lHyUtLS0t"
    "LS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLf/AABEIAAEAAQMB"
    "IgACEQEDEQH/xAAXAAADAQAAAAAAAAAAAAAAAAAAAQID/8QAFhABAQEAAAAAAAAAAAAAAAAA"
    "AAER/8QAFgEBAQEAAAAAAAAAAAAAAAAAAgAB/8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAwD"
    "AQACEQMRAD8A0wD/AP/Z"
)


def post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"{edge_url}{path}",
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


start = post("/api/v1/auth/start", {})
session_id = start["session_id"]

for _ in range(10):
    post("/api/v1/auth/frame", {"session_id": session_id, "frame": FRAME_DATA_URL})
    time.sleep(0.11)

finish = post("/api/v1/auth/finish", {"session_id": session_id})
if finish.get("decision") == "step_up":
    for _ in range(10):
        post("/api/v1/auth/frame", {"session_id": session_id, "frame": FRAME_DATA_URL})
        time.sleep(0.11)
    finish = post("/api/v1/auth/finish", {"session_id": session_id})

assert finish["decision"] in {"allow", "deny"}, f"Unexpected decision: {finish}"
assert "reason_codes" in finish, "reason_codes missing"
assert "risk_score" in finish, "risk_score missing"
print("Edge smoke test passed")
PY


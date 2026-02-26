#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen

CLOUD_URL = os.environ.get("CLOUD_URL", "http://127.0.0.1:8000").rstrip("/")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN") or os.environ.get("ADMIN_API_TOKEN")
WINDOW = os.environ.get("WINDOW", "24h")
OUT_PATH = Path(os.environ.get("OUT", "output/ci/reliability_slo.json"))

if not ADMIN_TOKEN:
    raise SystemExit("ADMIN_TOKEN (or ADMIN_API_TOKEN) is required")

request = Request(
    f"{CLOUD_URL}/v1/admin/stats?window={WINDOW}",
    headers={"X-Admin-Token": ADMIN_TOKEN},
)
with urlopen(request, timeout=20) as response:
    payload = json.loads(response.read().decode("utf-8"))

report = {
    "generated_at": datetime.now(UTC).isoformat(),
    "window": WINDOW,
    "cloud_url": CLOUD_URL,
    "metrics": {
        "events_ingested_count": payload.get("events_ingested_count"),
        "ingest_fail_count": payload.get("ingest_fail_count"),
        "liveness_failure_rate": payload.get("liveness_failure_rate"),
        "active_devices_window": payload.get("active_devices_window"),
        "outbox_pending_total": payload.get("outbox_pending_total"),
        "dlq_total": payload.get("dlq_total"),
        "latency_p50_ms": payload.get("latency_p50_ms"),
        "latency_p95_ms": payload.get("latency_p95_ms"),
    },
}

OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
OUT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(f"Wrote reliability SLO report: {OUT_PATH}")

# Phase 3 Quick Start Guide

Phase 3 is ready to test. Follow these steps to run the complete system.

## Prerequisites

Ensure you have:
- Docker and Docker Compose
- Python 3.11+ with venv activated
- Port 8000 (cloud) and 8787 (edge) available

## Step 1: Start Cloud Service

```bash
# Navigate to repository root
cd /path/to/SentinelID

# Start Postgres and Cloud services
docker-compose up --build
```

Wait for postgres to be healthy (you'll see "started" messages). The cloud service will:
- Initialize database tables
- Start on http://localhost:8000
- Be ready to accept telemetry

Verify:
```bash
curl http://localhost:8000/health
# Should return: {"status":"healthy"}
```

## Step 2: Start Edge Service (separate terminal)

```bash
cd /path/to/SentinelID/apps/edge

# Activate venv if not already
source .venv/bin/activate

# Set environment variables for telemetry
export TELEMETRY_ENABLED=true
export CLOUD_INGEST_URL=http://127.0.0.1:8000/v1/ingest/events
export EDGE_ENV=dev
export EDGE_AUTH_TOKEN=devtoken

# Start edge service (using poetry or uvicorn)
poetry run uvicorn sentinelid_edge.main:app --reload --host 127.0.0.1 --port 8787

# OR if poetry not available:
# uvicorn sentinelid_edge.main:app --reload --host 127.0.0.1 --port 8787
```

Verify edge is running:
```bash
curl -H "Authorization: Bearer devtoken" http://127.0.0.1:8787/api/v1/health
# Should return: {"status":"ok"}
```

## Step 3: Run Smoke Tests

### Test 3A: Authentication Flow with Telemetry

```bash
# In a new terminal, start authentication session
curl -X POST -H "Authorization: Bearer devtoken" \
  http://127.0.0.1:8787/api/v1/auth/start \
  -H "Content-Type: application/json" \
  -d '{}'

# Returns: {"session_id":"...", "challenges":[...]}
# Save the session_id for next step
```

### Test 3B: Finish Authentication (triggers audit + telemetry)

```bash
# Replace SESSION_ID with actual session_id from above
curl -X POST -H "Authorization: Bearer devtoken" \
  http://127.0.0.1:8787/api/v1/auth/finish \
  -H "Content-Type: application/json" \
  -d '{"session_id":"SESSION_ID"}'

# Returns: {"decision":"allow|deny", "reason_codes":[...], "liveness_passed":true}
```

This triggers:
1. Audit event written to .sentinelid/audit.db
2. Telemetry event sent to cloud ingest
3. Device registration (first time only)

### Test 3C: Verify Cloud Received Telemetry

```bash
# Check if events were ingested
curl http://127.0.0.1:8000/v1/admin/events?limit=5

# Should return: {"events":[...], "total":1}
```

### Test 3D: Verify Statistics

```bash
curl http://127.0.0.1:8000/v1/admin/stats

# Should return:
# {
#   "total_devices": 1,
#   "active_devices": 1,
#   "total_events": 1,
#   "allow_count": 1,
#   "deny_count": 0,
#   "error_count": 0
# }
```

## Step 4: Run Unit Tests

### Edge Tests

```bash
cd /path/to/SentinelID/apps/edge

# Run audit log tests
pytest tests/test_audit_log.py -v

# Run telemetry tests
pytest tests/test_telemetry.py -v

# Expected: 18+ tests passing
```

### Cloud Tests

```bash
cd /path/to/SentinelID/apps/cloud

# Run signature verification tests
pytest tests/test_signature_verification.py -v

# Expected: 7+ tests passing
```

## Troubleshooting

### Cloud won't start

```bash
# Check if port 8000 is available
lsof -i :8000

# Reset docker
docker-compose down --volumes
docker-compose up --build
```

### Edge won't start

```bash
# Check if cryptography is installed
pip list | grep cryptography

# Install if missing
pip install cryptography==41.0.7 httpx==0.25.1
```

### Can't connect to cloud from edge

```bash
# Verify cloud is running
curl http://127.0.0.1:8000/health

# Check CLOUD_INGEST_URL environment variable
echo $CLOUD_INGEST_URL

# Should be: http://127.0.0.1:8000/v1/ingest/events
```

### Telemetry not appearing in cloud

1. Verify `TELEMETRY_ENABLED=true`
2. Check edge logs for errors
3. Verify device is registered: `curl http://127.0.0.1:8000/v1/admin/stats`
4. Check audit log: `ls -la .sentinelid/audit.db`

## Files Created During Testing

After running the smoke test:

- `.sentinelid/audit.db` - SQLite audit log
- `.sentinelid/keys/device_keys.json` - Device keypair (ED25519)
- `.sentinelid/keys/device_id.json` - Device identifier

These are created locally on the edge device and are NOT synced to cloud.

## What Was Tested

Phase 3 validates:

1. Audit logging (hash-chain integrity maintained)
2. Device binding (keypair generation and storage)
3. Telemetry signing (ED25519 signatures)
4. Cloud ingest (signature verification, device registration)
5. Event persistence (Postgres storage)
6. Admin queries (filtering and pagination)
7. End-to-end flow (auth -> audit -> telemetry -> cloud)

## Next Steps

1. Merge feat/audit-telemetry-v0.3 to main
2. Tag v0.3.0
3. Deploy cloud service to production
4. Configure edge devices with production CLOUD_INGEST_URL

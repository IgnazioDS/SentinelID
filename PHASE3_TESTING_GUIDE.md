# Phase 3 Testing Guide

Complete end-to-end testing of audit logging, device binding, telemetry signing, and cloud ingest.

## Prerequisites

- Docker and Docker Compose (with build completed)
- Python 3.11+ virtual environment activated
- Ports 8000, 8787, 3000 available
- Cryptography package installed: `pip install cryptography==41.0.7 httpx==0.25.1`

## Test Sequence

### Phase 3A: Unit Tests (Local Testing)

Run tests directly in Python environment without Docker:

```bash
cd /path/to/SentinelID

# Test audit log hash-chain integrity
cd apps/edge
pytest tests/test_audit_log.py -v

# Test telemetry sanitization and signing
pytest tests/test_telemetry.py -v

# Test cloud signature verification
cd ../cloud
pytest tests/test_signature_verification.py -v
```

**Expected Results:**
- All 7 audit log tests pass (hash-chain integrity, event retrieval, chain verification)
- All 9 telemetry tests pass (sanitization, signing, no sensitive data)
- All 7 signature verification tests pass (ED25519 signature validation)

### Phase 3B: Integration Test - Docker Build and Services

#### Step 1: Build Docker Images

```bash
cd /path/to/SentinelID

# Build docker images
docker-compose build

# Verify images created
docker images | grep sentinelid
```

Expected output:
```
sentinelid-cloud          latest    ...
sentinelid-admin          latest    ...
sentinelid-postgres       ...
```

#### Step 2: Start Cloud Service

```bash
cd /path/to/SentinelID

# Start postgres and cloud services
docker-compose up -d postgres cloud

# Wait for postgres to be healthy (10-15 seconds)
sleep 15

# Verify cloud service is running
curl http://localhost:8000/health

# Expected response:
# {"status":"healthy"}
```

#### Step 3: Start Edge Service (Separate Terminal)

```bash
cd /path/to/SentinelID/apps/edge

# Activate venv if not already
source .venv/bin/activate

# Set environment variables
export TELEMETRY_ENABLED=true
export CLOUD_INGEST_URL=http://127.0.0.1:8000/v1/ingest/events
export EDGE_ENV=dev
export EDGE_AUTH_TOKEN=devtoken

# Start edge service
poetry run uvicorn sentinelid_edge.main:app --reload --host 127.0.0.1 --port 8787

# OR if poetry not available:
uvicorn sentinelid_edge.main:app --reload --host 127.0.0.1 --port 8787
```

Wait for: "Application startup complete"

### Phase 3C: Smoke Test - Authentication + Telemetry Flow

#### Test 1: Start Authentication Session

```bash
# In a new terminal
curl -X POST -H "Authorization: Bearer devtoken" \
  http://127.0.0.1:8787/api/v1/auth/start \
  -H "Content-Type: application/json" \
  -d '{}'

# Response example:
# {
#   "session_id": "550e8400-e29b-41d4-a716-446655440000",
#   "challenges": [...]
# }

# Save the session_id for next step
SESSION_ID="550e8400-e29b-41d4-a716-446655440000"
```

#### Test 2: Finish Authentication (Triggers Audit + Telemetry)

```bash
# Replace SESSION_ID with actual value from above
curl -X POST -H "Authorization: Bearer devtoken" \
  http://127.0.0.1:8787/api/v1/auth/finish \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SESSION_ID\"}"

# Response example:
# {
#   "decision": "allow",
#   "reason_codes": ["LIVENESS_PASSED"],
#   "liveness_passed": true
# }

# This triggers:
# 1. Audit event written to .sentinelid/audit.db
# 2. Telemetry event sent to cloud ingest
# 3. Device registration (first time only)
```

#### Test 3: Verify Cloud Received Telemetry

```bash
# Give cloud 2 seconds to ingest
sleep 2

# Retrieve ingested events
curl http://127.0.0.1:8000/v1/admin/events?limit=5

# Expected response:
# {
#   "events": [
#     {
#       "event_id": "...",
#       "device_id": "...",
#       "timestamp": 1234567890,
#       "outcome": "allow",
#       "reason_codes": ["LIVENESS_PASSED"],
#       "liveness_passed": true,
#       ...
#     }
#   ],
#   "total": 1
# }
```

#### Test 4: Verify Statistics

```bash
# Get service statistics
curl http://127.0.0.1:8000/v1/admin/stats

# Expected response:
# {
#   "total_devices": 1,
#   "active_devices": 1,
#   "total_events": 1,
#   "allow_count": 1,
#   "deny_count": 0,
#   "error_count": 0
# }
```

### Phase 3D: Audit Log Inspection

Verify audit log was created and contains hash chain:

```bash
# Check if audit log exists
ls -la ~/.sentinelid/audit.db

# Expected: SQLite database file created

# Check audit log contents (requires sqlite3)
sqlite3 ~/.sentinelid/audit.db "SELECT event_id, outcome, hash FROM audit_events LIMIT 5;"

# Verify device keys were created
ls -la ~/.sentinelid/keys/

# Expected:
# - device_keys.json (ED25519 keypair)
# - device_id.json (Device identifier)
```

### Phase 3E: Multiple Auth Cycles

Run authentication multiple times to verify telemetry batching:

```bash
# Run auth cycle 5 times
for i in {1..5}; do
  # Start session
  RESPONSE=$(curl -s -X POST -H "Authorization: Bearer devtoken" \
    http://127.0.0.1:8787/api/v1/auth/start \
    -H "Content-Type: application/json" -d '{}')

  SESSION_ID=$(echo $RESPONSE | jq -r '.session_id')

  # Finish session
  curl -s -X POST -H "Authorization: Bearer devtoken" \
    http://127.0.0.1:8787/api/v1/auth/finish \
    -H "Content-Type: application/json" \
    -d "{\"session_id\":\"$SESSION_ID\"}"

  echo "Auth cycle $i completed"
  sleep 1
done

# Wait for telemetry export
sleep 5

# Verify all events reached cloud
curl http://127.0.0.1:8000/v1/admin/events?limit=100 | jq '.total'

# Expected: At least 5 events
```

## Troubleshooting

### Cloud Service Issues

**Port already in use:**
```bash
lsof -i :8000
kill -9 <PID>
docker-compose down --volumes
```

**Docker network issues:**
```bash
docker-compose down
docker system prune -f
docker-compose up --build
```

**Database connection errors:**
```bash
# Check postgres is healthy
docker-compose logs postgres

# Reset database
docker-compose down --volumes
docker-compose up -d postgres
sleep 15
docker-compose up -d cloud
```

### Edge Service Issues

**Module import errors:**
```bash
pip install cryptography==41.0.7 httpx==0.25.1
```

**Telemetry not reaching cloud:**
```bash
# Verify telemetry is enabled
echo $TELEMETRY_ENABLED  # Should be 'true'

# Check cloud URL
echo $CLOUD_INGEST_URL   # Should be http://127.0.0.1:8000/v1/ingest/events

# Verify cloud is running
curl http://127.0.0.1:8000/health
```

**Auth endpoints return 404:**
```bash
# Verify correct path includes /api/v1 prefix
# Correct: /api/v1/auth/start
# Wrong: /v1/auth/start
```

## Verification Checklist

- [ ] Docker images build successfully
- [ ] postgres service starts and is healthy
- [ ] cloud service starts on port 8000
- [ ] edge service starts on port 8787
- [ ] /api/v1/auth/start endpoint responds
- [ ] /api/v1/auth/finish endpoint responds
- [ ] Audit events written to .sentinelid/audit.db
- [ ] Device keys created in .sentinelid/keys/
- [ ] Telemetry events received by cloud
- [ ] Cloud statistics show correct counts
- [ ] Multiple auth cycles work correctly
- [ ] All unit tests pass locally

## Security Checklist

- [ ] Telemetry contains NO raw images or embeddings
- [ ] Telemetry signed with device ED25519 key
- [ ] Cloud verifies signatures before accepting events
- [ ] Device keys stored locally only (not synced to cloud)
- [ ] Audit log has hash-chain integrity (can detect tampering)
- [ ] Bearer token authentication enforced
- [ ] Cloud service isolated to localhost only
- [ ] Edge service isolated to localhost only

## Files Created During Testing

After successful smoke test:

```
.sentinelid/
├── audit.db                  # SQLite hash-chained audit log
├── keys/
│   ├── device_keys.json      # ED25519 keypair (private)
│   └── device_id.json        # Device identifier
```

These files remain on the edge device and are NOT synced to cloud (they stay local for security).

## Next Steps

Once all tests pass:

1. Run full test suite: `pytest tests/ -v`
2. Review audit log integrity
3. Validate telemetry signatures
4. Check cloud database for event consistency
5. Document any issues encountered

## Phase 3 Summary

This test validates:
- Audit logging with hash-chain integrity
- Device binding (ED25519 keypair generation)
- Telemetry signing and sanitization
- Cloud ingest with signature verification
- Automatic device registration
- End-to-end auth → audit → telemetry → cloud flow

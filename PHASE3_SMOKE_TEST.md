# Phase 3 Smoke Test & Deployment Guide

## Running Cloud Service with Docker Compose

### Prerequisites
- Docker and Docker Compose installed
- Python 3.11+ (for edge testing)
- PostgreSQL client tools (optional, for direct DB inspection)

### Start Cloud Service

```bash
# Navigate to repository root
cd /path/to/SentinelID

# Start all services (Postgres + Cloud)
docker-compose up --build

# In another terminal, check health
curl http://localhost:8000/health
```

Response should be:
```json
{"status": "healthy"}
```

### Environment Variables

Cloud service uses these PostgreSQL connection details:
```
DATABASE_URL=postgresql://admin:password@postgres/sentinelid
```

Configure cloud endpoints for edge:
```bash
# In edge device environment
export TELEMETRY_ENABLED=true
export CLOUD_INGEST_URL=http://localhost:8000/v1/ingest/events
export TELEMETRY_BATCH_SIZE=10
export TELEMETRY_MAX_RETRIES=3
```

## Smoke Test Scenarios

### Test 1: Device Registration & Telemetry Ingest

This test verifies that edge devices can register and send telemetry to cloud.

```bash
# Step 1: Generate test keypair (simulates edge device)
python3 << 'EOF'
from sentinelid_edge.services.security.crypto import CryptoProvider
import json

private_pem, public_pem = CryptoProvider.generate_keypair()
print("Private Key (keep secret):")
print(private_pem)
print("\nPublic Key (register with cloud):")
print(public_pem)
EOF
```

Save the keys for use below.

### Test 2: Send Signed Telemetry Batch

```bash
# Create test telemetry event
curl -X POST http://localhost:8000/v1/ingest/events \
  -H "Content-Type: application/json" \
  -d '{
    "batch_id": "test-batch-1",
    "device_id": "device-12345",
    "timestamp": 1708025400,
    "device_public_key": "-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----",
    "batch_signature": "0123456789abcdef...",
    "events": [
      {
        "event_id": "event-1",
        "device_id": "device-12345",
        "timestamp": 1708025400,
        "event_type": "auth_finished",
        "outcome": "allow",
        "reason_codes": ["LIVENESS_PASSED"],
        "liveness_passed": true,
        "similarity_score": 0.95,
        "signature": "0123456789abcdef..."
      }
    ]
  }'
```

Expected response (HTTP 202):
```json
{
  "status": "accepted",
  "batch_id": "test-batch-1",
  "events_ingested": 1,
  "device_registered": true
}
```

### Test 3: Retrieve Ingested Events

```bash
# Get latest 10 events
curl http://localhost:8000/v1/admin/events?limit=10

# Filter by device_id
curl "http://localhost:8000/v1/admin/events?limit=10&device_id=device-12345"

# Filter by outcome
curl "http://localhost:8000/v1/admin/events?limit=10&outcome=allow"
```

Expected response:
```json
{
  "events": [
    {
      "event_id": "event-1",
      "device_id": "device-12345",
      "timestamp": 1708025400,
      "event_type": "auth_finished",
      "outcome": "allow",
      "reason_codes": ["LIVENESS_PASSED"],
      "liveness_passed": true,
      "similarity_score": 0.95,
      "ingested_at": "2025-02-22T10:30:00+00:00"
    }
  ],
  "total": 1
}
```

### Test 4: Retrieve Cloud Statistics

```bash
curl http://localhost:8000/v1/admin/stats
```

Expected response:
```json
{
  "total_devices": 1,
  "active_devices": 1,
  "total_events": 1,
  "allow_count": 1,
  "deny_count": 0,
  "error_count": 0
}
```

### Test 5: Signature Verification Failure

Send request with invalid signature:

```bash
curl -X POST http://localhost:8000/v1/ingest/events \
  -H "Content-Type: application/json" \
  -d '{
    "batch_id": "bad-batch",
    "device_id": "device-999",
    "timestamp": 1708025400,
    "device_public_key": "-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----",
    "batch_signature": "invalid_signature_0000000000000000000000",
    "events": [
      {
        "event_id": "event-bad",
        "device_id": "device-999",
        "timestamp": 1708025400,
        "event_type": "auth_finished",
        "outcome": "allow",
        "reason_codes": ["TEST"],
        "signature": "invalid_signature_0000000000000000000000"
      }
    ]
  }'
```

Expected response (HTTP 401):
```json
{"detail": "Invalid batch signature"}
```

## Edge Integration Tests

### Test Edge Audit Logging

```bash
# Run edge tests for audit log integrity
cd apps/edge
pytest tests/test_audit_log.py -v

# Expected output:
# test_audit_event_creation PASSED
# test_audit_event_write PASSED
# test_hash_chain_integrity PASSED
# test_chain_integrity_verification PASSED
# test_event_retrieval PASSED
```

### Test Edge Telemetry Sanitization

```bash
# Run telemetry tests
pytest tests/test_telemetry.py -v

# Expected output:
# test_telemetry_event_no_raw_data PASSED
# test_telemetry_mapper_sanitization PASSED
# test_telemetry_to_dict_no_none_values PASSED
# test_telemetry_event_signing PASSED
```

### Test Cloud Signature Verification

```bash
# Run cloud tests
cd apps/cloud
pytest tests/test_signature_verification.py -v

# Expected output:
# test_event_signature_valid PASSED
# test_event_signature_invalid PASSED
# test_batch_signature_valid PASSED
# test_signature_verification_different_keys PASSED
```

## Database Inspection

Connect directly to Postgres to verify data:

```bash
# Connect to Postgres
psql -h localhost -U admin -d sentinelid -W

# View registered devices
SELECT device_id, public_key, registered_at, is_active FROM devices;

# View ingested events
SELECT event_id, device_id, event_type, outcome, ingested_at FROM telemetry_events;

# Count events by outcome
SELECT outcome, COUNT(*) FROM telemetry_events GROUP BY outcome;
```

## Full End-to-End Test (Local Only)

1. Start cloud service: `docker-compose up --build`
2. In edge service, set `TELEMETRY_ENABLED=true`
3. Run edge auth endpoint: `POST /api/v1/auth/start`
4. Complete authentication flow: `POST /api/v1/auth/frame`, `POST /api/v1/auth/finish`
5. Verify audit event written locally: `.sentinelid/audit.db`
6. Check telemetry sent to cloud: `curl http://localhost:8000/v1/admin/events`

## Troubleshooting

### Cloud service won't start
```bash
# Check if port 8000 is in use
lsof -i :8000

# Check Postgres is healthy
docker-compose logs postgres

# Rebuild containers
docker-compose down --volumes
docker-compose up --build
```

### Signature verification failing
- Verify public key is properly formatted (PEM format)
- Check signature is hex-encoded (128 chars for ED25519)
- Ensure canonical JSON ordering (use `json.dumps(payload, sort_keys=True)`)

### Events not appearing in cloud
- Verify `TELEMETRY_ENABLED=true` on edge
- Check edge logs for export errors
- Verify batch signature is valid
- Check device registration: `curl http://localhost:8000/v1/admin/stats`

## Security Checklist

Phase 3 maintains security posture:

- [x] Bearer token enforcement on edge (localhost-only)
- [x] ED25519 signatures on all telemetry
- [x] No raw images or embeddings in telemetry
- [x] Hash-chained audit log (append-only)
- [x] Device registration with public key verification
- [x] Signature verification before event storage
- [x] Sensitive data not persisted to disk
- [x] Database credentials not hardcoded (use env vars)

## Next Steps

After successful smoke test:
1. Run full test suite: `pytest tests/ -v`
2. Merge feature branch to main
3. Tag release: `v0.3.0`
4. Deploy cloud to production environment
5. Configure edge devices with production CLOUD_INGEST_URL

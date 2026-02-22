# SentinelID Telemetry Recovery Guide (Phase 5)

## Overview

This guide covers disaster recovery and troubleshooting for the telemetry exporter with outbox pattern. The system uses a Dead Letter Queue (DLQ) to isolate and recover undeliverable events.

## Core Concepts

### Outbox Table States

The `outbox_events` table tracks all telemetry events with three states:

| State | Meaning | Action | Next Step |
|-------|---------|--------|-----------|
| PENDING | Ready to send | System attempts delivery | → SENT or back to PENDING (retry) |
| SENT | Successfully delivered | No action | Event lifecycle complete |
| DLQ | Max retries exceeded | Manual intervention required | Replay to PENDING or investigate |

### Retry Strategy

- **Initial delay:** 1 second
- **Exponential backoff:** Doubles after each attempt
  - Attempt 1: 1s
  - Attempt 2: 2s
  - Attempt 3: 4s
  - Attempt 4: 8s
  - Attempt 5: 16s
- **Max attempts:** 5 (configurable)
- **After max:** Event moved to DLQ

Timeline: ~31 seconds total before DLQ

## Monitoring

### Check Outbox Status

Connect to edge device and query diagnostics:

```bash
# Get current outbox stats
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/diagnostics

# Response includes:
{
  "outbox": {
    "pending_count": 5,
    "dlq_count": 2,
    "sent_count": 1500
  },
  "dlq_preview": [
    {
      "id": 1001,
      "created_at": "2026-02-22T10:30:00",
      "attempts": 5,
      "last_error": "Connection refused"
    }
  ]
}
```

### Check Database Directly

```bash
# Access edge device SQLite database
sqlite3 /path/to/.sentinelid/audit.db

# View pending events
sqlite> SELECT id, created_at, attempts, status FROM outbox_events 
        WHERE status = 'PENDING' LIMIT 10;

# View DLQ events
sqlite> SELECT id, created_at, attempts, last_error FROM outbox_events 
        WHERE status = 'DLQ';

# View statistics
sqlite> SELECT 
          COUNT(CASE WHEN status = 'PENDING' THEN 1 END) as pending,
          COUNT(CASE WHEN status = 'DLQ' THEN 1 END) as dlq,
          COUNT(CASE WHEN status = 'SENT' THEN 1 END) as sent
        FROM outbox_events;
```

## Recovery Procedures

### Scenario 1: Cloud Service Temporarily Unavailable

**Symptoms:**
- Pending count increasing
- Last_error shows connection refused/timeout
- DLQ count still 0

**Recovery:**
1. Wait for cloud service to recover
2. System will automatically retry pending events
3. Monitor pending count decrease
4. No manual intervention needed

**Timeline:** Events retry automatically within 30 seconds

### Scenario 2: Network Connectivity Issues

**Symptoms:**
- Intermittent DLQ movement
- Last_error shows "Temporary failure"
- Some events move to DLQ while others succeed

**Recovery:**

```bash
# Step 1: Verify network connectivity
ping <cloud-ingest-server>

# Step 2: Check cloud service is reachable
curl http://<cloud-ingest-server>/health

# Step 3: Once connectivity restored, replay DLQ
curl -X POST \
  -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/replay-dlq \
  -H "Content-Type: application/json"

# Response: { "replayed": 5, "status": "success" }
```

### Scenario 3: Cloud Ingest Format Incompatibility

**Symptoms:**
- All new events moving to DLQ
- Last_error shows "HTTP 400" or "JSON validation error"
- Never worked before

**Recovery:**

1. **Check cloud ingest API version compatibility:**

```bash
# Get edge version
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/diagnostics | grep status

# Get cloud ingest version
curl http://<cloud-server>/v1/health
```

2. **Verify payload format:**

```bash
# Inspect DLQ event payload
sqlite3 /path/to/.sentinelid/audit.db
sqlite> SELECT payload_json FROM outbox_events 
        WHERE status = 'DLQ' LIMIT 1;

# Compare with cloud ingest API documentation
```

3. **Update edge service if needed:**

```bash
# Stop edge service
killall sentinelid_edge

# Update to compatible version
cd apps/edge
git pull  # or update to specific branch

# Restart and retry
# In Tauri app, use start_edge command
```

4. **Replay after fix:**

```bash
curl -X POST \
  -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/replay-dlq
```

### Scenario 4: Database Corruption

**Symptoms:**
- SQLite errors in edge logs
- Unable to query outbox table
- Edge service crashes on startup

**Recovery:**

```bash
# Step 1: Backup corrupted database
cp .sentinelid/audit.db .sentinelid/audit.db.backup

# Step 2: Reset outbox (WARNING: loses pending events)
sqlite3 .sentinelid/audit.db
sqlite> DELETE FROM outbox_events WHERE status IN ('PENDING', 'DLQ');
sqlite> VACUUM;
sqlite> .quit

# Step 3: Restart edge service
# Events will start fresh

# Note: Events already deleted cannot be recovered
# Consider exporting DLQ events before deletion
```

**Export DLQ Before Deletion:**

```bash
# Export to JSON for external processing
sqlite3 .sentinelid/audit.db << 'SQL'
.mode json
SELECT id, created_at, payload_json, attempts, last_error 
FROM outbox_events 
WHERE status = 'DLQ' 
ORDER BY created_at DESC;
SQL
```

### Scenario 5: Device Storage Full

**Symptoms:**
- New events not being added
- "No space left on device" errors
- DLQ count not changing

**Recovery:**

```bash
# Step 1: Check disk space
df -h

# Step 2: Clean up old events (keep last 24 hours)
sqlite3 .sentinelid/audit.db
sqlite> DELETE FROM outbox_events 
        WHERE status = 'SENT' 
        AND created_at < datetime('now', '-1 day');
sqlite> VACUUM;
sqlite> .quit

# Step 3: Verify space recovered
du -h .sentinelid/audit.db
```

## Manual Recovery Commands

### Replay All DLQ Events

```bash
# Using REST API
curl -X POST \
  -H "Authorization: Bearer $(cat .sentinelid/edge_token)" \
  http://localhost:8000/api/v1/replay-dlq
```

### Replay Specific DLQ Event

```bash
# Direct database manipulation
sqlite3 .sentinelid/audit.db
sqlite> UPDATE outbox_events 
        SET status = 'PENDING', attempts = 0
        WHERE id = 1001 AND status = 'DLQ';
sqlite> .quit

# Edge will retry on next export cycle
```

### View Event Payload

```bash
# Pretty-print event payload
sqlite3 .sentinelid/audit.db
sqlite> SELECT json_indent(payload_json) 
        FROM outbox_events 
        WHERE id = 1001;
```

## Prevention Strategies

### 1. Health Monitoring

```bash
# Monitor every 5 minutes
while true; do
  curl -H "Authorization: Bearer <token>" \
    http://localhost:8000/api/v1/diagnostics | \
    jq '.outbox | select(.dlq_count > 0)'
  sleep 300
done
```

### 2. Automatic Replay Schedule

```bash
# Cron job to replay DLQ daily
0 2 * * * curl -X POST \
  -H "Authorization: Bearer $EDGE_TOKEN" \
  http://localhost:8000/api/v1/replay-dlq
```

### 3. Database Maintenance

```bash
# Weekly cleanup of old SENT events
0 3 * * 0 sqlite3 .sentinelid/audit.db \
  "DELETE FROM outbox_events WHERE status = 'SENT' AND created_at < datetime('now', '-30 days'); VACUUM;"
```

## Testing Recovery

### Test DLQ Behavior

```bash
# Simulate delivery failure by stopping cloud service
systemctl stop cloud-service  # or equivalent

# Generate telemetry events
# Monitor DLQ filling up

# Restart cloud service
systemctl start cloud-service

# Trigger replay
curl -X POST \
  -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/replay-dlq

# Verify events are retried
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/diagnostics | jq '.outbox'
```

## Logging and Diagnostics

### Enable Debug Logging

Set in edge environment:
```bash
LOGLEVEL=DEBUG
```

### View Exporter Logs

```bash
# In docker or system logs
grep "telemetry\|exporter\|outbox" /var/log/sentinelid/edge.log

# Useful patterns
grep "Telemetry export failed" logs  # Failures
grep "Exported telemetry batch" logs # Successes
grep "moved to DLQ" logs             # DLQ movements
```

## Escalation Path

1. **Device Level:** Check local database and DLQ count
2. **Edge Service:** Review exporter logs and last error
3. **Cloud Service:** Verify ingest endpoint health
4. **Network:** Check connectivity and firewall rules
5. **Escalate:** If unresolved, contact support with:
   - DLQ event samples (JSON)
   - Edge version and configuration
   - Cloud service version
   - Network topology diagram

## Reference

- Outbox Pattern: Event Sourcing pattern for reliable messaging
- Dead Letter Queue: Queue for messages that cannot be delivered
- Exponential Backoff: Retry strategy that increases wait time
- Implementation: apps/edge/sentinelid_edge/services/storage/repo_outbox.py

See PACKAGING.md for desktop bundling information.

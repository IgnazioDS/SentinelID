# Telemetry Recovery

For environment setup and service startup commands, use `RUNBOOK.md`.

## Scope

This guide covers recovery of telemetry delivery using the edge outbox and DLQ model.

## Outbox States

- `PENDING`: queued for delivery.
- `SENT`: delivered successfully.
- `DLQ`: retries exhausted, requires operator action.

## Diagnostics

### API-level diagnostics

```bash
curl -H "Authorization: Bearer <edge-token>" http://127.0.0.1:8787/api/v1/diagnostics
```

Inspect `pending_count`, `dlq_count`, `sent_count`, and recent error metadata.

### Database-level diagnostics

```bash
sqlite3 apps/edge/.sentinelid/audit.db
```

Useful queries:

```sql
SELECT id, status, attempts, created_at, last_error
FROM outbox_events
ORDER BY id DESC
LIMIT 25;
```

```sql
SELECT status, COUNT(*) FROM outbox_events GROUP BY status;
```

## Recovery Procedures

### Cloud unavailable

- Keep edge running.
- Restore cloud service.
- Pending events retry automatically.

### DLQ growth after transient outage

- Validate cloud health endpoint.
- Confirm ingest URL configured on edge (`CLOUD_INGEST_URL`).
- Replay or reset failed entries after root-cause resolution.

### Local database corruption

1. Backup first.
2. Remove or repair corrupted db.
3. Restart edge.

Example reset:

```bash
cp apps/edge/.sentinelid/audit.db apps/edge/.sentinelid/audit.db.backup
rm -rf apps/edge/.sentinelid
```

### Storage pressure

- Check disk free space.
- Prune old `SENT` rows if retention policy allows.

## Operational Guardrails

- Do not delete DLQ rows before capturing `last_error` and payload context.
- Prefer replay after fixing connectivity or schema mismatch root causes.
- Keep cloud/admin token and URL configuration consistent across `.env` and runtime exports.

## Related Docs

- Privacy controls: `docs/privacy.md`
- Threat model: `docs/threat-model.md`
- Key lifecycle: `docs/KEY_MANAGEMENT.md`

# Privacy

For setup and operational commands, use `RUNBOOK.md`.

## Implemented (v0.6)

### Data Minimisation

- Face embeddings (float vectors) are computed on-device and are never
  transmitted to the cloud.
- Raw camera frames are processed in memory only and are never written to
  disk or included in telemetry.
- Telemetry events contain only anonymised metadata: outcome (allow/deny),
  liveness boolean, similarity score, risk score, session duration. The
  Pydantic ingest model enforces extra = "forbid" so that any attempt to
  submit frames, embeddings, landmarks, or raw face metadata is rejected at
  the API boundary with a 422 error.

### Encryption at Rest

- All face embeddings are stored as AES-256-GCM encrypted blobs in the local
  SQLite database. The database never contains plaintext float vectors.
- The master key is stored in the OS keychain (macOS) when available; a
  restricted file (mode 0600) is used as a fallback.
- Per-template keys are derived via HKDF-SHA256(master_key, template_id, salt)
  so that compromise of one derived key does not expose the master key or any
  sibling.

### Identity Deletion

- POST /api/v1/settings/delete_identity removes all templates, optionally
  clears the audit log and telemetry outbox, and rotates or destroys the device
  keypair and master encryption key.
- After deletion, stored blobs are permanently unreadable because the master key
  is destroyed. There is no recovery path.

### Audit Logging

- The local audit log records only outcome-level data (allow/deny, reason codes,
  scores) and never raw biometric data.
- Hash-chain integrity protects the log against tampering.

### Sensitive Field Logging

- Bearer tokens, admin tokens, and raw embeddings are never written to logs.
- Token values appearing in log entries are replaced with a short SHA-256 prefix
  (8 hex characters) for correlation purposes only.

### Rate Limiting and Lockout

- Auth endpoints are protected by a token bucket (10-burst, 2 req/s sustained)
  and an escalating lockout policy (30 s after 5 failures, up to 5 min).
- This mitigates brute-force attacks against the local authentication API.

---

## Planned

- Differential privacy noise for aggregate telemetry statistics.
- On-device audit log encryption (currently stored in plaintext in SQLite).
- Formal data-retention policy and automatic expiry of old telemetry events.
- Secure enclave / TPM integration for master key storage on non-macOS platforms.
- User-visible consent flow before first enrollment.

# Threat Model

For setup and operational commands, use `RUNBOOK.md`.

## Implemented Mitigations (v0.6)

### T1: Database Theft

Threat: Attacker obtains a copy of the SQLite database file.

Mitigation (implemented):
- All face embeddings are AES-256-GCM encrypted. Without the master key (stored
  in the OS keychain, not in the database), the attacker cannot recover any
  biometric data.
- Audit event payloads are encrypted at rest with per-event derived keys, while
  hash-chain links remain verifiable.
- The GCM authentication tag detects any tampering with stored blobs.

Residual risk: If the attacker also obtains the OS keychain (e.g., via a
malicious process running as the same OS user), they can decrypt the database.
Mitigation: Rely on OS account separation and full-disk encryption.

---

### T2: Brute Force / Credential Stuffing Against Local API

Threat: Attacker sends many requests to /auth/start, /auth/frame, or
/auth/finish to probe for valid biometrics or to exhaust resources.

Mitigation (implemented):
- Token bucket per (endpoint, client key): 10-burst, 2 req/s for auth endpoints.
- Escalating lockout: 30 s after 5 failures, doubling up to 5 min after 40+.
- Lockout state is persisted on disk, so Edge process restart does not reset lockout history.
- Frame cap per session: sessions are terminated after MAX_FRAMES_PER_SESSION
  (default 200) to prevent indefinite probing within a single session.
- Request body size limit (2 MB) prevents resource exhaustion via large payloads.

---

### T3: Man-in-the-Middle on Edge-to-Cloud Channel

Threat: Attacker intercepts telemetry batches in transit.

Mitigation (implemented):
- Every telemetry event and batch is signed with the device ED25519 private key.
- Cloud verifies signatures; unsigned or incorrectly signed events are rejected.
- Telemetry never includes biometric data (enforced by Pydantic extra=forbid).
- Edge startup enforces secure ingest transport in production: non-loopback
  `CLOUD_INGEST_URL` values must use HTTPS.

Residual risk: Certificate pinning is not enforced. mTLS is supported via
optional client cert/key configuration, but deployments must enable it.

---

### T4: Compromised Admin Token

Threat: ADMIN_API_TOKEN is leaked and an attacker gains read access to the
cloud admin endpoints.

Mitigation (implemented):
- hmac.compare_digest prevents timing oracle attacks on token comparison.
- Token value is never logged; only a short SHA-256 hash prefix is recorded.
- Admin endpoints are read-only (query/stats); they cannot modify data.

Residual risk: A leaked token grants full read access to event metadata. Token
rotation requires redeployment.

---

### T5: Malicious Telemetry Submission

Threat: A rogue edge device attempts to submit privacy-violating data (frames,
embeddings, landmarks) to the cloud.

Mitigation (implemented):
- Pydantic models on the cloud ingest endpoint use extra = "forbid".
- Field validators enforce that event_type and outcome are within allowed sets.
- Any payload containing forbidden fields is rejected with HTTP 422.
- Tests enforce that _FORBIDDEN_FIELDS constant covers the minimum required set.
- Edge outbox automatically expires old `SENT` telemetry rows (default 30 days).

---

### T6: Master Key Exposure During Rotation

Threat: A crash or network failure during key rotation leaves the database in a
partially-re-encrypted state, making some templates unreadable.

Mitigation (implemented):
- Key rotation wraps all blob updates in a single SQLite BEGIN EXCLUSIVE
  transaction. On failure the transaction is rolled back; the old key remains
  active and all templates remain readable.
- The new master key is persisted only after the transaction commits
  successfully.

---

### T7: Identity Left on Device After User Request to Delete

Threat: A user requests identity deletion but residual data remains.

Mitigation (implemented):
- POST /api/v1/settings/delete_identity deletes templates, optionally clears
  the audit log and telemetry outbox, rotates the device keypair, and destroys
  the master encryption key.
- The response includes deletion counts for user confirmation.

Residual risk: SQLite WAL or backup files may contain old data pages. Full
secure deletion requires OS-level secure erase.

---

## Planned Mitigations

- Secure enclave / TPM integration for master key storage on Linux / Windows.

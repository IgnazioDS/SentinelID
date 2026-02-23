# SentinelID v0.6 - Security Hardening Changelog

## v0.6.0 (2026-02-23)

### Security - Encryption at Rest

- AES-256-GCM embedding encryption with self-describing blob format (SENC magic header, version, salt, nonce, ciphertext+tag)
- Master key stored in macOS Keychain via keyring library; env var SENTINELID_MASTER_KEY as dev fallback; restricted file as secondary fallback
- Per-template key derived via HKDF-SHA256(master_key, info="sentinelid-template-v1:<template_id>", salt=<per-blob random>)
- SQLite database never contains plaintext float vectors
- TemplateRepository provides store/load/list/delete/delete_all/rewrap_all operations

### Security - Key Rotation

- POST /api/v1/admin/rotate-key endpoint (localhost-only, bearer-protected)
- Rotation is transaction-safe: all blob rewraps run in a single SQLite EXCLUSIVE transaction; on failure the old key remains active and the DB is unchanged
- New master key is persisted only after successful transaction commit
- Response includes count of rewrapped templates

### Security - Identity Deletion

- POST /api/v1/settings/delete_identity endpoint
- Deletes all enrolled templates
- Optionally clears local audit log (clear_audit=true)
- Optionally clears telemetry outbox and DLQ (clear_outbox=true)
- Optionally rotates device ED25519 keypair and device_id (rotate_device_key=true)
- Destroys master encryption key (keychain + fallback file)
- Response includes deletion counts for each category

### Security - Rate Limiting and Lockout

- Token bucket per (endpoint, client key): 10-burst / 2 req/s for auth endpoints, 30-burst / 10 req/s for others
- Escalating lockout: 30 s after 5 failures, 60 s after 10, 120 s after 20, 300 s after 40+
- Failure counter resets on successful authentication
- Rate limiter runs before bearer token verification to block brute force probing

### Security - Input Hardening

- RequestSizeLimitMiddleware rejects requests exceeding MAX_REQUEST_BODY_BYTES (default 2 MB on edge, 5 MB on cloud)
- Frame counter per session: sessions terminate with 429 after MAX_FRAMES_PER_SESSION (default 200)
- Session lifetime enforced by existing session_timeout_seconds (120 s default)
- Sensitive fields (token values, raw embeddings) are not logged; only short SHA-256 hash prefixes for correlation

### Security - Cloud Hardening

- Admin token comparison uses hmac.compare_digest (timing-safe)
- Admin token value never logged; only 8-char SHA-256 prefix
- RequestSizeLimitMiddleware added to cloud service (5 MB limit)
- Telemetry ingest models use extra="forbid" to reject raw frames, embeddings, landmarks, face metadata
- event_type and outcome field validators enforce allowed value sets

### Configuration

New environment variables:
- SENTINELID_DB_PATH (edge) - SQLite database path
- SENTINELID_KEYCHAIN_DIR (edge) - key storage directory
- SENTINELID_MASTER_KEY (edge) - hex-encoded master key for dev/CI
- MAX_REQUEST_BODY_BYTES (edge) - max request body size in bytes
- MAX_FRAMES_PER_SESSION (edge) - max frames per auth session
- MAX_SESSION_LIFETIME_SECONDS (edge) - max session duration
- CLOUD_MAX_REQUEST_BODY_BYTES (cloud) - max request body size

### Tests

83 new tests (58 edge + 25 cloud), all passing:
- test_encryption.py: HKDF derivation, AES-GCM roundtrip, tamper detection, MasterKeyProvider
- test_template_repo.py: encrypted storage, no plaintext in DB, rewrap atomicity
- test_rate_limit.py: token bucket, lockout escalation, client isolation
- test_delete_identity.py: endpoint coverage, auth guard
- test_telemetry_forbidden_fields.py: rejects all forbidden fields; fails if constant is incomplete

### Documentation

- docs/KEY_MANAGEMENT.md: key hierarchy, blob format, rotation procedure, deletion semantics
- docs/privacy.md: Implemented vs Planned sections
- docs/threat-model.md: T1-T7 threat mitigations with residual risks

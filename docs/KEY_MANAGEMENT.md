# Key Management

This document describes the cryptographic key hierarchy used by SentinelID Edge,
the rotation procedure, and the identity-deletion semantics.

---

## Key Hierarchy

```
OS Keychain / SENTINELID_MASTER_KEY env var
          |
          v
    Master Key (AES-256, 32 bytes)
          |
          | HKDF-SHA256(master_key, info="sentinelid-template-v1:<template_id>", salt=<per-blob salt>)
          |
          v
    Per-Template Key (AES-256, 32 bytes)
          |
          v
    AES-256-GCM encrypted embedding blob in SQLite
```

### Device Signing Keys

A separate ED25519 keypair is managed by `Keychain` (services/security/keychain.py):

- Private key: stored in `.sentinelid/keys/device_keys.json` (mode 0600)
- Public key: registered with Cloud on first telemetry batch
- Device ID: SHA256(public_key)[:32] as a UUID string

Device keys are used exclusively for signing telemetry batches; they are not
used for encryption.

---

## Master Key Storage

Priority order at startup:

1. **macOS Keychain** (via `keyring` library)
   - Service: `com.sentinelid.edge`
   - Account: `master_encryption_key`
   - Value: 64 hex characters (32 bytes)

2. **Environment variable** `SENTINELID_MASTER_KEY`
   - Must be exactly 64 hex characters
   - Suitable for CI and development; not recommended in production

3. **Fallback file** `.sentinelid/keys/master_key.hex`
   - Created automatically when neither keychain nor env var is available
   - Mode 0600 (owner read/write only)
   - Used only when `keyring` is unavailable

If none of these exist, a fresh key is generated and stored using the best
available method.

---

## Encrypted Blob Format

Every face embedding is stored as an encrypted blob with the following layout:

```
Offset  Length  Field
------  ------  -----
0       4       Magic bytes: 0x53454E43 ("SENC")
4       1       Version: 0x01
5       16      Per-blob random salt (used in HKDF)
21      12      AES-GCM nonce (random per encryption)
33      N+16    AES-GCM ciphertext + 128-bit authentication tag
```

Additional Authenticated Data (AAD) bound to each ciphertext:
```
"template:<template_id>"
```

This ensures that a ciphertext encrypted for template A cannot be substituted
for template B without detection.

---

## Key Rotation

Rotation replaces the master key without any downtime or data loss.

### Endpoint

```
POST /api/v1/admin/rotate-key
Authorization: Bearer <EDGE_AUTH_TOKEN>
```

Access is restricted to localhost (127.0.0.1 / ::1).

### Rotation Algorithm

1. Generate a new 32-byte master key in memory (not persisted yet).
2. For each template in the database:
   a. Decrypt the existing blob using the old master key.
   b. Re-encrypt using the new master key (new salt + nonce).
3. All UPDATE statements are wrapped in a single SQLite `BEGIN EXCLUSIVE`
   transaction. If any step fails, the transaction is rolled back and the
   old key remains active. The database is never left in a partially-rotated
   state.
4. On success, persist the new key to the OS keychain (or fallback file).
5. Update the in-memory key cache.

### Response

```json
{
  "status": "rotated",
  "templates_rewrapped": 5,
  "rotated_at": 1700000000
}
```

### Manual Rotation (CLI)

```bash
curl -s -X POST http://127.0.0.1:8765/api/v1/admin/rotate-key \
  -H "Authorization: Bearer $(cat .sentinelid/edge_token)" | jq .
```

---

## Identity Deletion

```
POST /api/v1/settings/delete_identity
Authorization: Bearer <EDGE_AUTH_TOKEN>
Content-Type: application/json

{
  "clear_audit":       true,
  "clear_outbox":      true,
  "rotate_device_key": true
}
```

All fields default to `true`.

### What Is Deleted

| Data                      | Controlled by       | Effect                                               |
|---------------------------|---------------------|------------------------------------------------------|
| Face embedding templates  | always              | All rows deleted from `templates` table              |
| Master encryption key     | always              | Removed from keychain and fallback file; future blobs unreadable |
| Audit log                 | `clear_audit`       | All rows deleted from `audit_events` table           |
| Telemetry outbox / DLQ    | `clear_outbox`      | All rows deleted from `outbox_events` table          |
| Device keypair            | `rotate_device_key` | New ED25519 key generated; new device_id derived     |

When `rotate_device_key=false` the keypair is regenerated on the next boot.

### Response

```json
{
  "status": "deleted",
  "templates_deleted": 3,
  "audit_events_deleted": 42,
  "outbox_events_deleted": 7,
  "device_key_rotated": true,
  "deleted_at": 1700000000
}
```

---

## Security Properties

- **Forward secrecy for templates**: Each blob uses a unique random salt, so
  re-using the same master key and template_id still produces a different derived
  key per blob (HKDF with unique salt).

- **Template isolation**: Compromising the derived key for one template does not
  reveal the master key or derived keys for any other template.

- **Authenticated encryption**: AES-256-GCM provides both confidentiality and
  integrity. Any tampering with a stored blob is detected at decryption time.

- **Key deletion is permanent**: After `delete_identity`, all encrypted blobs are
  unreadable because the master key is destroyed. There is no recovery mechanism.

---

## Threat Model Assumptions

- The OS user account running the edge service is trusted.
- The SQLite database file is stored on the local file system and protected by OS
  file permissions.
- The master key stored in the OS keychain is protected by macOS Keychain access
  controls (user login required to unlock).
- The environment variable fallback (`SENTINELID_MASTER_KEY`) is suitable for
  development only. In production, rely on the OS keychain.

# SentinelID

SentinelID is a desktop-first biometric authentication platform.

It pairs a local edge verifier with cloud telemetry and an admin dashboard, so authentication decisions stay local while operations stay observable.

## Architecture

```text
+------------------+        localhost (token, loopback only)        +------------------+
| Desktop (Tauri)  |  -------------------------------------------->  | Edge (FastAPI)   |
| Camera UX + UX   |                                                  | Verify/Liveness  |
+------------------+                                                  | Audit + Signing  |
                                                                      +---------+--------+
                                                                                |
                                                                                | Signed, sanitized telemetry
                                                                                v
                                                                      +---------+--------+
                                                                      | Cloud (FastAPI)  |
                                                                      | Ingest + Admin   |
                                                                      +---------+--------+
                                                                                |
                                                                                | HTTP API
                                                                                v
                                                                      +------------------+
                                                                      | Admin (Next.js)  |
                                                                      | Events/Stats     |
                                                                      +------------------+
```

## Security Posture

- Local API is bound to localhost and protected by bearer token auth.
- No iframe/browser embedding trust path for auth decisions.
- Edge produces signed telemetry; cloud verifies signatures before persistence.
- Audit logging is hash-chained for tamper evidence.
- Telemetry is sanitized: no raw frames, no embeddings, no landmarks.

## Quickstart

For complete setup and command reference, use:

- [`RUNBOOK.md`](RUNBOOK.md)

Typical flow:

1. Start edge service locally.
2. Run desktop app in Tauri dev mode.
3. Start cloud/admin stack with Docker Compose.
4. Run smoke tests and component tests.

## Durable Documentation

- Architecture: [`docs/architecture.md`](docs/architecture.md)
- API: [`docs/api.md`](docs/api.md)
- Privacy: [`docs/privacy.md`](docs/privacy.md)
- Threat model: [`docs/threat-model.md`](docs/threat-model.md)
- Evaluation: [`docs/evaluation.md`](docs/evaluation.md)
- Packaging: [`docs/PACKAGING.md`](docs/PACKAGING.md)
- Recovery: [`docs/RECOVERY.md`](docs/RECOVERY.md)
- Key management: [`docs/KEY_MANAGEMENT.md`](docs/KEY_MANAGEMENT.md)
- Changelog: [`CHANGELOG.md`](CHANGELOG.md)

## Contributing

- Follow the run/test workflow in [`RUNBOOK.md`](RUNBOOK.md).
- Keep docs centralized: operational commands in `RUNBOOK.md`, release notes in `CHANGELOG.md`.

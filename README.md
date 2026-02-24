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

Use `RUNBOOK.md` as the authoritative command path.

Common commands:

```bash
make test
make docker-build
make release-check
```

## CI Coverage

GitHub Actions runs the following on PRs and `main` pushes:

- edge pytest
- cloud pytest
- desktop web build + cargo check
- docker compose build (cloud + admin)

## Documentation

- Runbook: [`RUNBOOK.md`](RUNBOOK.md)
- Release process: [`docs/RELEASE.md`](docs/RELEASE.md)
- API: [`docs/api.md`](docs/api.md)
- Architecture: [`docs/architecture.md`](docs/architecture.md)
- Privacy: [`docs/privacy.md`](docs/privacy.md)
- Threat model: [`docs/threat-model.md`](docs/threat-model.md)
- Evaluation: [`docs/evaluation.md`](docs/evaluation.md)
- Packaging: [`docs/PACKAGING.md`](docs/PACKAGING.md)
- Recovery: [`docs/RECOVERY.md`](docs/RECOVERY.md)
- Key management: [`docs/KEY_MANAGEMENT.md`](docs/KEY_MANAGEMENT.md)
- Changelog: [`CHANGELOG.md`](CHANGELOG.md)

## Contributing

- Follow `RUNBOOK.md` for run/test commands.
- Keep release notes in `CHANGELOG.md` and release steps in `docs/RELEASE.md`.

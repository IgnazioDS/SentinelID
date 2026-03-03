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
- Admin dashboard and `/api/cloud/*` proxy use server-side session auth (HttpOnly cookie); browser-supplied admin tokens are ignored.
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

Docker-first local startup:

```bash
make demo-up
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:3000
make demo-down
```

## Quick Demo

One command from repo root:

```bash
make demo
```

`make demo` is interactive and blocks until the desktop app is closed.
For CI-like non-interactive validation, use:

```bash
make demo-verify
```

Expected demo flow:

1. Enroll template in Desktop `Enroll` tab.
2. Login in `Login` tab (normal ALLOW path).
3. Trigger and complete STEP_UP path.
4. Observe telemetry/admin data in `http://127.0.0.1:3000`.
5. Generate sanitized support bundle from Desktop Settings or Admin Support page.

Interactive operator checklist:

- [`docs/DEMO_CHECKLIST.md`](docs/DEMO_CHECKLIST.md)
- `make demo-checklist`

## Desktop UX (v1.9.0)

The desktop app now follows a clear three-tab flow:

- `Login`: live camera preview, challenge instructions, progress meter, and step-up continuation state.
- `Enroll`: start/capture/commit wizard with real-time quality feedback.
- `Settings`: demo mode, telemetry/exporter health, reset identity, and support bundle action.

Status strip fields are always visible: service status, camera status, and last sync timestamp.

Screenshot placeholders for release artifacts:

- `docs/images/desktop-login-placeholder.png`
- `docs/images/desktop-enroll-placeholder.png`
- `docs/images/desktop-settings-placeholder.png`

## CI Coverage

GitHub Actions runs the following on PRs and `main` pushes:

- edge pytest
- cloud pytest
- desktop web build + cargo check
- docker compose build (cloud + admin)
- release parity gate on PR + `main` (`make release-check`)

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
- Demo checklist: [`docs/DEMO_CHECKLIST.md`](docs/DEMO_CHECKLIST.md)
- Key management: [`docs/KEY_MANAGEMENT.md`](docs/KEY_MANAGEMENT.md)
- Changelog: [`CHANGELOG.md`](CHANGELOG.md)

## Contributing

- Follow `RUNBOOK.md` for run/test commands.
- Keep release notes in `CHANGELOG.md` and release steps in `docs/RELEASE.md`.

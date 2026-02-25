# Changelog

All notable changes to SentinelID are documented in this file.

## v1.1.0 (2026-02-25)

### Cloud Schema Management
- Replaced cloud startup `Base.metadata.create_all()` path with Alembic migrations.
- Added cloud Alembic scaffolding under `apps/cloud/alembic/` plus baseline schema migration.
- Added cloud migration helper (`apps/cloud/migrations.py`) and startup migration execution via `alembic upgrade head`.

### Operations
- Updated cloud container startup to wait for Postgres readiness, run migrations, then launch uvicorn (`apps/cloud/scripts/start_cloud.sh`).
- Wired Docker Compose cloud service to use migration-aware startup command.

### Tests
- Added migration regression coverage to ensure startup never calls `Base.metadata.create_all`.
- Added migration bootstrapping test on a fresh sqlite database and idempotent re-run check.

### Documentation
- Updated `RUNBOOK.md` with manual Alembic migration commands and migration workflow guidance.

## v1.0.2 (2026-02-25)

### Security
- Added edge localhost-only middleware guard that rejects non-loopback clients with `403` (health endpoints remain publicly reachable).
- Added edge tests covering localhost access and non-local rejection behavior.

### Documentation
- Updated `RUNBOOK.md` with pipx-based Poetry install instructions for PEP 668-safe macOS setups.
- Made Docker Compose the recommended cloud/admin runtime path and documented local cloud Python compatibility (`3.11` to `3.13`).
- Added explicit three-terminal local run workflow (cloud/admin, edge, desktop) and clarified edge health endpoints (`/health` and `/api/v1/health`).

### Build / Stability
- Added `make dev-edge` target so runbook commands map directly to available Makefile targets.
- Verified `docker compose build admin` succeeds with existing App Router root layout.

## v1.0.0 (2026-02-25)

### Added
- CI pipelines under `.github/workflows/`:
  - `edge-tests.yml`
  - `cloud-tests.yml`
  - `desktop-build.yml`
  - `docker-build.yml`
- Cloud test dependency manifest at `apps/cloud/requirements-dev.txt`.
- Release preflight automation script: `scripts/release/checklist.sh`.
- App Router root layout for admin UI: `apps/admin/app/layout.tsx`.

### Changed
- `RUNBOOK.md` is now the authoritative v1.0.0 command path and aligns with Makefile targets.
- `Makefile` expanded with explicit test/build/docker/smoke/perf/release-check targets.
- Admin pages now use stable relative imports for `lib/api`.
- Admin API client uses `Headers` to avoid TypeScript build incompatibilities.
- Admin dependencies now include a deterministic lockfile (`apps/admin/package-lock.json`).

### Fixed
- Next.js admin build failure caused by missing App Router root layout.
- Docker admin build failure path caused by missing root layout during `next build`.

### Release Process
- Updated `docs/RELEASE.md` with v1.0.0 tagging rules (`v1.0.0-rc.N`, `v1.0.0`) and pre-tag checklist.

## v0.7.0 (2026-02-23)

### Added
- Evaluation harness at `scripts/eval/run_eval.sh` for repeated authentication runs with sanitized JSON output.
- Risk policy tuning controls: `RISK_THRESHOLD_R1`, `RISK_THRESHOLD_R2`, and `MAX_STEP_UPS_PER_SESSION`.

### Changed
- Policy flow supports a risk-based step-up path (`ALLOW` / `STEP_UP` / `DENY`) with reproducible demo guidance.

## v0.6.0 (2026-02-23)

### Security - Encryption at Rest
- AES-256-GCM embedding encryption with a self-describing blob format.
- Master key storage via OS keychain, with development fallback options.
- HKDF-SHA256 per-template key derivation.

### Security - Key Rotation
- Added `POST /api/v1/admin/rotate-key` (localhost-only, bearer-protected).
- Rotation is transaction-safe; all template rewrap operations are atomic.

### Security - Identity Deletion
- Added `POST /api/v1/settings/delete_identity`.
- Supports template deletion, optional audit/outbox cleanup, and optional device key rotation.
- Destroys master encryption key after deletion.

### Security - Rate Limiting and Lockout
- Token-bucket rate limiting and escalating lockout for auth endpoints.
- Lockout resets on successful authentication.

### Security - Input and Cloud Hardening
- Request body size limits on edge and cloud services.
- Max-frame and session-lifetime enforcement for auth sessions.
- Timing-safe admin token comparison and strict telemetry ingest validation.

### Tests
- Added broad edge/cloud coverage for encryption, rotation, lockout, identity deletion, and forbidden telemetry fields.

### Documentation
- Added `docs/KEY_MANAGEMENT.md`.
- Updated `docs/privacy.md` and `docs/threat-model.md` with implemented mitigations.

## v0.5.0 (2026-02-22)

### Added
- Desktop bundling workflow via `scripts/bundle_edge_venv.sh` and `make bundle-edge`.
- Durable telemetry outbox with retry and DLQ handling.
- Diagnostics endpoint and request-ID middleware for observability.
- Bundling smoke tests and outbox repository tests.

### Changed
- Desktop runtime supports bundled edge launcher in production builds.
- Build/test workflow formalized in root `Makefile`.

### Documentation
- Added packaging and telemetry recovery guides:
  - `docs/PACKAGING.md`
  - `docs/RECOVERY.md`

## v0.4.0 (historical)

### Added
- Admin dashboard and cloud admin endpoints for events, devices, and stats.
- Token-protected admin API and local Docker Compose stack for cloud/admin/postgres.

## v0.3.0 (historical)

### Added
- Hash-chained audit logging on edge.
- Device binding and ED25519 telemetry signing.
- Cloud ingest service with signature verification and automatic device registration.
- Admin query endpoints and Postgres persistence.

## v0.2.0 (historical)

### Added
- Active liveness challenge flow (blink/head-turn) and policy-driven auth decisions.
- Desktop camera UX for challenge progression and auth result handling.

## v0.1.0 (historical)

### Added
- Initial edge + desktop loopback authentication scaffold.

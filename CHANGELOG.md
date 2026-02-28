# Changelog

All notable changes to SentinelID are documented in this file.

## v2.3.1 (2026-02-27)

### Pilot Readiness Freeze
- Completed pilot freeze runbook alignment and evidence workflow for Docker-first self-hosted validation.
- Hardened `scripts/release/build_pilot_evidence_index.sh` to auto-detect latest successful `release-parity` run URLs for pull requests and `main` pushes when not provided explicitly.
- Extended pilot evidence capture to include successful `release-tag` `workflow_dispatch` run proof URLs (auto-detected on `main` when available, or injected via `RELEASE_TAG_DISPATCH_URL`).
- Standardized release-facing version headers to `v2.3.1` for pilot tag readiness.
- Added manual `workflow_dispatch` support and concurrency controls for `.github/workflows/release-tag.yml` to allow post-release pipeline validation without creating a new tag.

## v2.3.0 (2026-02-27)

### DX / Forward Compatibility
- Migrated edge Poetry config from deprecated `[tool.poetry.dev-dependencies]` to `[tool.poetry.group.dev.dependencies]` to remove Poetry deprecation warnings in local/CI runs.
- Added targeted pytest warning filters for third-party `asyncio.iscoroutinefunction` deprecation noise emitted by current FastAPI/Starlette internals on newer Python runtimes.

### Drift Cleanup
- Replaced placeholder edge package author metadata with the project maintainer identity.
- Updated cloud service API metadata version to `2.3.0` to match current release line and reduce release/docs drift.

## v2.2.1 (2026-02-27)

### Reliability Control Hardening
- Tightened cloud bind defaults in `apps/cloud/scripts/start_cloud.sh`:
  - uses `127.0.0.1` for non-container local runs when `CLOUD_BIND_HOST` is unset
  - uses `0.0.0.0` for container runtime (`/.dockerenv` or `CONTAINER_RUNTIME=1`)
  - still respects explicit `CLOUD_BIND_HOST` overrides

### Deterministic Failure Diagnostics
- Added release-check failure diagnostic capture in `scripts/release/checklist.sh`, including summary metadata, edge log tails, and docker compose state/log snapshots under `output/ci/logs/`.
- Added cloud smoke and recovery smoke diagnostic exports under `output/ci/logs/` for failed health/recovery runs.

## v2.2.0 (2026-02-27)

### CI Parity Hardening
- Hardened `.github/workflows/release-parity.yml` with explicit read-only workflow permissions and branch/ref concurrency control.
- Added retry-aware parity runner `scripts/ci/run_release_parity.sh` to rerun `make release-check` once after a failed attempt, with compose cleanup between attempts.
- Updated parity workflow to collect and upload deterministic diagnostics (`output/ci/logs/release_check_attempt_*.log`, compose `ps` and compose logs) alongside existing release artifacts.

### Merge Gate Policy
- Documented and enforced `release-parity` as the required release-integrity gate while preserving existing fast CI workflows (`edge-tests`, `cloud-tests`, `desktop-build`, `docker-build`) for rapid feedback.

## v2.1.1 (2026-02-27)

### Release Integrity + Doc Alignment
- Updated release-facing version headers to `v2.1.1` across `RUNBOOK.md`, `docs/RELEASE.md`, `docs/DEMO_CHECKLIST.md`, and the Makefile help banner.
- Extended `scripts/release/check_version_consistency.sh` to enforce version alignment for `docs/DEMO_CHECKLIST.md` in addition to changelog/runbook/release guide/Make help text.
- Updated release documentation to explicitly define the canonical orphan check command path (`scripts/check_no_orphan_edge.sh`) and retain the release-path wrapper as compatibility-only.

### Script Path Consistency
- Switched `scripts/release/checklist.sh` and `scripts/demo_verify.sh` to invoke the canonical orphan check path directly to avoid operator ambiguity.

## v2.1.0 (2026-02-26)

### Admin Security Hardening
- Replaced public-token admin proxy model with server-side session authentication.
- Added admin session routes: `POST /api/admin/session/login`, `POST /api/admin/session/logout`, and `GET /api/admin/session/me`.
- Added middleware protection for admin routes and cloud proxy routes.
- Updated proxy behavior to reject unauthenticated access, strip browser-provided `X-Admin-Token`, and inject server-side `ADMIN_API_TOKEN`.
- Added login page and shell sign-out action for authenticated admin access.

### Runtime and Config Contract Updates
- Removed `NEXT_PUBLIC_ADMIN_TOKEN` from runtime config paths.
- Added server-only admin auth env vars: `ADMIN_UI_USERNAME`, `ADMIN_UI_PASSWORD_HASH`, `ADMIN_UI_SESSION_SECRET`, and `ADMIN_UI_SESSION_TTL_MINUTES`.
- Added `CLOUD_BIND_HOST` support with safer local default (`127.0.0.1`) and explicit container bind override (`0.0.0.0`).

### Release Integrity and Automation
- Added `scripts/release/check_version_consistency.sh` and integrated it into `make release-check`.
- Added reusable support bundle sanitization validator: `scripts/check_support_bundle_sanitization.sh`.
- Added release-path wrapper `scripts/release/check_no_orphan_edge.sh` for consistent orphan-check invocation.
- Added client bundle exposure check: `scripts/release/check_no_public_admin_token_bundle.sh`.
- Added release evidence pack builder: `scripts/release/build_evidence_pack.sh` and `make release-evidence`.
- Added pilot evidence index builder: `scripts/release/build_pilot_evidence_index.sh` and `make pilot-evidence`.
- Hardened release checklist to enforce:
  - no `NEXT_PUBLIC_ADMIN_TOKEN` in runtime config
  - no admin token leakage in client build artifacts
  - compose admin auth wiring
  - reliability SLO report generation
  - support bundle artifact capture and evidence pack generation

### CI Parity
- Added `.github/workflows/release-parity.yml` for PR + `main` release-hardening parity.
- Release parity workflow now executes full `make release-check` and uploads evidence artifacts.
- Added manual `demo-desktop-verify` workflow for GUI-capable runners to validate scripted demo close behavior.

### Reliability and Deprecation Cleanup
- Removed deprecated `datetime.utcnow()` usage in edge/cloud runtime paths.
- Migrated Pydantic v2 config patterns from legacy `class Config` to `ConfigDict`/`SettingsConfigDict`.
- Hardened `scripts/perf/bench_edge.py` with retry handling and deterministic diagnostics for transient `429/502/503/504` and retryable network failures.

### Documentation
- Updated runbook env/auth guidance for session-based admin auth.
- Replaced outdated release guide content with v2.1.0 release process and required evidence model.
- Added non-interactive `make demo-verify` flow, optional scripted desktop close verification, and explicit demo exit semantics in docs.
- Added pilot readiness freeze guide and pilot evidence index instructions.

## v2.0.0 (2026-02-26)

### Demo Mode and Operator Flow
- Added one-command demo targets: `make demo-up`, `make demo-desktop`, `make demo`, and `make demo-down`.
- Added `docs/DEMO_CHECKLIST.md` with a strict 10-step operator regression flow for portfolio demos.
- Added `make demo-checklist` to print/open the checklist quickly.

### Release Gating Hardening
- Extended `scripts/release/checklist.sh` with a mandatory demo-readiness section.
- Demo gating now requires: demo stack health, cloud recovery smoke, support-bundle sanitization checks, and desktop bundling smoke.

### Desktop Edge-Case Robustness
- Hardened camera initialization handling with explicit paths for blocked permissions, missing camera devices, and device-in-use errors.
- Added stronger retry/cancel paths across login/enroll state transitions to avoid deadlock states.
- Added TypeScript state-machine recovery assertions and switched Tauri dev edge spawn to Poetry-backed `edge_env.sh` launcher to avoid wrong-venv leakage.

### Admin Demo Ergonomics
- Added admin demo badge and top-bar correlation-id usage hint.
- Added events quick actions for `Last 15 min` and filtering by current device id.

### Documentation Polish
- Updated `README.md`, `RUNBOOK.md`, `docs/PACKAGING.md`, and `docs/RECOVERY.md` for demo-first onboarding.

## v1.9.0 (2026-02-26)

### Desktop UX Polish
- Replaced the single-screen desktop experience with explicit `Login`, `Enroll`, and `Settings` tabs.
- Added a persistent bottom status strip with service status, camera status, and diagnostics-driven last sync information.
- Added a clear step-up handoff view (`Additional check required`) before automatic continuation of secondary challenges.

### Flow Clarity and Error Handling
- Improved login and enrollment states with progress bars, challenge instructions, quality feedback, and result summaries.
- Added centralized reason-code to user-message mapping for auth/enrollment outcomes and quality gates.
- Added guarded runtime handling so browser-opened UI shows a friendly desktop-runtime-required message instead of raw Tauri internals errors.
- Standardized desktop API error handling into network/auth/config/server classes with actionable user-facing copy.

### Settings and Supportability
- Expanded Settings tab with Demo Mode, telemetry toggle/status, outbox/DLQ counters, last export error summary, and identity reset flow.
- Added desktop-triggered support bundle download action against cloud admin endpoint (when desktop env vars are configured).
- Added optional desktop support env vars and screenshot placeholder documentation for release QA.

## v1.8.0 (2026-02-26)

### Developer Experience Stability
- Hardened `make dev-edge` to always run through Poetry-managed edge runtime with explicit dependency preflight (`pydantic_settings`, `uvicorn`) to prevent wrong-venv leakage.
- Added `make check-edge-preflight` and `make edge-shell` for consistent edge environment checks and troubleshooting.
- Added edge import smoke test to catch startup-time dependency regressions (`pydantic_settings` + app import path).

### Desktop Runtime Consistency
- Added `make check-tauri-config` plus JSON validation for required Tauri metadata in both desktop config files.
- Fixed `make dev-desktop` pathing so Tauri dev/build execute from `src-tauri` consistently (no package-info config mismatch).
- Standardized desktop Tauri config versions to `1.8.0`.

### Admin/Compose Networking Consistency
- Standardized admin cloud env wiring to `NEXT_PUBLIC_CLOUD_BASE_URL` and `NEXT_PUBLIC_ADMIN_TOKEN`.
- Updated Docker Compose to use in-network cloud URL (`http://cloud:8000`) for admin container runtime.
- Added admin-side cloud proxy route (`/api/cloud/...`) so browser clients use same-origin requests while server resolves cloud service name.
- Improved admin API error message when cloud base URL config is missing.

### Release and Runbook Hardening
- Updated release checklist with devx checks (edge preflight, tauri config validation, compose admin env wiring).
- Added optional cloud recovery smoke toggle in release checklist (`RUN_CLOUD_RECOVERY_SMOKE=1`).
- Updated RUNBOOK and `.env.example` to document hardened env vars, preflight targets, and venv footgun warning.
- Updated admin smoke script to verify UI proxy path and cloud connectivity through admin server.

## v1.7.0 (2026-02-26)

### Admin UX and Operations
- Added a stable admin shell with left navigation (`Overview`, `Events`, `Devices`, `Support`) and a shared top bar for time range (`24h`, `7d`, `30d`) and search.
- Rebuilt the overview dashboard with real API-backed cards and charts (events over time, outcome breakdown, exporter lag trends).
- Upgraded events exploration with richer filters (`device_id`, `request_id`, `session_id`, `outcome`, `reason_code`, time range/search), pagination controls, and an event detail drawer with copy affordances.
- Upgraded devices view with reliability columns and per-device drill-down (`/devices/{device_id}`) showing recent events and outcome/reliability trends.
- Added support operations page with token-protected support bundle generation and direct download flow.

### Cloud Admin APIs
- Extended `/v1/admin/events` filtering with `reason_code`, `start_ts`, `end_ts`, and free-text `q`.
- Added `/v1/admin/events/series` for chart-friendly timeseries aggregation.
- Extended `/v1/admin/stats` to support windowed metrics and reliability totals.
- Added `/v1/admin/devices/{device_id}` for drill-down details.
- Added `/v1/admin/support-bundle` for sanitized tarball generation in-cloud.

### Tests and Smokes
- Added cloud integration coverage for new admin endpoints and support-bundle response validation.
- Hardened `scripts/smoke_test_admin.sh` to validate series/device-detail/support-bundle paths.

## v1.6.0 (2026-02-25)

### Correlation IDs
- Standardized `X-Request-Id` propagation on edge and cloud request middleware.
- Added request/session correlation fields through edge audit + telemetry payloads.
- Cloud now persists `request_id` and `session_id` on telemetry events and supports admin filtering by both.

### Structured Logging
- Added structured logging configuration for edge and cloud with `LOG_FORMAT=json|text` and `LOG_LEVEL`.
- Logs now emit consistent fields (`ts`, `level`, `service`, `request_id`, `session_id`, `device_id`, `event_id`).
- Added log redaction for token/signature-style fields and bearer credentials.

### Admin Reliability Metrics
- Extended cloud admin stats with ingest reliability counters and per-device health summaries.
- Added supportability fields from telemetry (`outbox_pending_count`, `dlq_count`, `last_error_summary`) for exporter lag visibility.

### Supportability Tooling
- Added `scripts/support_bundle.sh` to generate sanitized support tarballs under `scripts/support/out/`.
- Updated runbook and recovery docs with support bundle usage.
- Hardened smoke scripts to assert and print request correlation headers.

## v1.5.0 (2026-02-25)

### Edge Exporter Durability
- Extended outbox durability metadata with persisted `last_attempt_at`, `last_success_at`, and sanitized `last_error` summaries.
- Added jittered exponential retry scheduling and restart-safe replay semantics for `PENDING`/`DLQ` transitions.
- Added localhost-only, bearer-protected DLQ replay endpoint: `POST /api/v1/admin/outbox/replay-dlq`.

### Cloud Ingest Idempotency
- Updated ingest handling to accept duplicate retry batches idempotently (existing `event_id` rows are counted as duplicates, not reinserted).
- Preserved uniqueness guarantees (`event_id` constraint) while avoiding retry-induced duplicate writes.

### Diagnostics + Recovery
- Expanded edge diagnostics with reliability-first fields:
  - `outbox_pending_count`, `dlq_count`
  - `last_attempt`, `last_success`, `last_error_summary`
  - `telemetry_flags`
- Added outage recovery smoke script: `scripts/smoke_test_cloud_recovery.sh`.
- Updated release checklist to include cloud-down recovery validation.
- Updated `RUNBOOK.md` and `docs/RECOVERY.md` with replay and recovery flow details.

### Desktop Reliability
- Hardened Tauri edge lifecycle to recover from crashed child process by restarting with a fresh port/token on the next command path.
- Updated desktop API client to refresh edge connection metadata and retry once across edge restarts.

### Tests
- Added edge coverage for jittered retry metadata, error sanitization, bulk DLQ replay, replay endpoint behavior, and diagnostics reliability fields.
- Added cloud ingest idempotency coverage (retry of same payload does not create duplicate rows).

## v1.4.0 (2026-02-25)

### Desktop Distribution
- Standardized bundled edge launcher at `apps/desktop/resources/edge/run_edge.sh` with loopback-only startup and runtime env wiring (`EDGE_PORT`, `EDGE_AUTH_TOKEN`, `EDGE_ENV`).
- Updated Tauri production startup to launch bundled edge resources (not Poetry) while preserving existing dev-mode source startup.
- Added edge process shutdown handling on desktop app exit to avoid orphaned child processes.

### Packaging Tooling
- Reworked `scripts/bundle_edge_venv.sh` to build a clean bundled venv, install deterministic runtime dependencies, install edge wheel, and verify `uvicorn`.
- Added bundled fallback source copy under `apps/desktop/resources/edge/app/` for controlled runtime import fallback.
- Updated ignore rules to keep bundled runtime artifacts local-only (`pyvenv/`, `app/`).

### Smoke Validation
- Hardened `scripts/smoke_test_bundling.sh` into a deterministic distribution smoke path with dynamic port selection, health waits, explicit auth-gating assertion (`401`), and timeout-based failure output.

### Documentation
- Updated `RUNBOOK.md` with distribution build guidance, dev vs production edge startup behavior, and no-Poetry runtime sanity command.
- Updated `docs/PACKAGING.md` with bundled layout, clean-machine verification steps, and troubleshooting guidance (Gatekeeper, permissions, port conflicts).

## v1.3.0 (2026-02-25)

### CI / Release Gating
- Updated PR and `main` CI workflows for edge tests, cloud tests, desktop build checks, and docker image builds with dependency caching.
- Added tag-triggered release workflow (`v*.*.*`) that reruns gating checks and uploads edge benchmark artifacts (`scripts/perf/out/*.json`, optional logs).

### Release Automation Hardening
- Hardened release checklist orchestration with explicit step tracking, strict exit behavior, and concise pass/fail summary output.
- Aligned release-check path with CI parity commands (`test-edge`, `test-cloud`, `build-desktop-web`, `check-desktop-rust`, `docker-build`) plus smoke/perf validation.

### Smoke + Perf Scripts
- Hardened smoke scripts for deterministic behavior:
  - required env var validation
  - service health wait loops
  - strict assertions and clear failure messages
- Standardized benchmark output artifacts under `scripts/perf/out/` and added ignore rules for generated JSON/log files.

### Documentation
- Updated `RUNBOOK.md` to keep Docker Compose as the beginner-first path and document cloud local-dev Python constraints (`3.11` to `3.13`) with pyenv setup guidance.

## v1.2.0 (2026-02-25)

### Verification Hardening
- Made fallback embeddings explicit: production now rejects model-unavailable verification with `MODEL_UNAVAILABLE` instead of silently degrading.
- Added `ALLOW_FALLBACK_EMBEDDINGS` (dev-only opt-in). When fallback is used, responses include `FALLBACK_EMBEDDING_USED`.
- Extended reason-code catalog for model availability and explicit fallback reporting.

### Enrollment + Quality
- Tightened enrollment/verification quality gating with explicit `FACE_TOO_SMALL`, `TOO_BLURRY`, `POSE_TOO_LARGE`, `TOO_DARK`, `NO_FACE`, and `MULTIPLE_FACES`.
- Enrollment pipeline now propagates model-unavailable failures explicitly and continues storing encrypted templates from aggregated embeddings.

### Evaluation
- Added `scripts/eval/calibrate_threshold.sh` to generate local FAR/FRR calibration reports under `scripts/eval/out/`.
- Updated `docs/evaluation.md` with calibration dataset format and report interpretation.

### Tests
- Added v1.2 coverage for fallback mode controls, model-unavailable endpoint behavior, enrollment lifecycle paths, and policy boundary precedence.

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

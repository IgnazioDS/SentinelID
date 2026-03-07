# SentinelID Runbook (v2.5.0)

This is the single source of truth for local setup, run, and validation.

## Prerequisites

- macOS or Linux
- Python 3.11+
- Node.js 18+
- Rust toolchain (Tauri)
- Docker + `docker compose`

## Install Poetry (pipx, PEP 668-safe)

On macOS with Homebrew Python, install Poetry via `pipx`:

```bash
brew install pipx
pipx ensurepath
pipx install poetry==1.8.2
poetry --version
```

If `poetry` is not on your PATH yet, restart your shell.

## Environment

```bash
cp .env.example .env
```

Required values:

- `EDGE_AUTH_TOKEN`
- `ADMIN_API_TOKEN`
- `ADMIN_UI_USERNAME`
- `ADMIN_UI_PASSWORD_HASH` (bcrypt hash for non-Docker runs; keep bcrypt values single-quoted in `.env`) or `ADMIN_UI_PASSWORD_HASH_B64` (recommended for Docker Compose)
- `ADMIN_UI_SESSION_SECRET`
- In `EDGE_ENV=prod`, device and master-key initialization require OS keychain access by default. Use `ALLOW_KEYCHAIN_FALLBACK=1` only for controlled debugging when fallback storage is unavoidable.

Optional values:

- `ADMIN_UI_SESSION_TTL_MINUTES` (default `480`)
- `ADMIN_UI_SESSION_SECURE` (default `0`; set `1` only behind HTTPS)
- `CLOUD_BIND_HOST` (unset defaults to `127.0.0.1` for local non-container runs and `0.0.0.0` for container runtime)
- `CLOUD_INGEST_URL` must use `https://` in `EDGE_ENV=prod` unless host is loopback (`localhost`, `127.0.0.1`, `::1`)
- `TELEMETRY_TLS_CA_BUNDLE_PATH` (optional custom CA bundle for telemetry TLS verification)
- `TELEMETRY_MTLS_CERT_PATH` + `TELEMETRY_MTLS_KEY_PATH` (optional client certificate/key pair for telemetry mTLS; requires `CLOUD_INGEST_URL` with `https://`)
- `TELEMETRY_TLS_CERT_SHA256_PINS` (optional comma-separated SHA-256 server certificate fingerprints; requires `CLOUD_INGEST_URL` with `https://`)
- `TELEMETRY_TLS_MIN_PIN_COUNT_PROD` (default `2`; minimum pin overlap required in production when pinning is enabled)
- `TELEMETRY_TLS_ALLOW_SINGLE_PIN_PROD` (default `0`; set `1` only for controlled bootstrap/rotation windows)
- `TELEMETRY_TRANSPORT_PREFLIGHT_ON_START` (default `0`; set `1` to run a live telemetry transport preflight at edge startup)
- `TELEMETRY_TRANSPORT_PREFLIGHT_TIMEOUT_SECONDS` (default `5.0`; TLS probe timeout for startup/manual transport preflight)
- `TELEMETRY_SENT_RETENTION_DAYS` (default `30`; set `0` to disable automatic SENT outbox expiry)
- `TELEMETRY_RETENTION_SWEEP_INTERVAL_SECONDS` (default `3600`)
- `SENTINELID_LOCKOUT_STATE_PATH` (default `.sentinelid/lockout_state.json`)
- `ADMIN_UI_PASSWORD` (dev/smoke helper for scripted admin login only)

Preflight note:

- `make release-check` now fails when secret values in `.env` contain unescaped `$`. Use single quotes around bcrypt hashes or populate `ADMIN_UI_PASSWORD_HASH_B64` for Docker Compose.
- `make release-check` also writes `output/ci/invariant_report.json` and `output/ci/desktop_warning_budget.json` for release triage. The invariant report should stay fully green; the warning budget summary fails when desktop Rust warnings exceed `DESKTOP_WARNING_BUDGET`.

Optional verification fallback toggle (dev only):

- `ALLOW_FALLBACK_EMBEDDINGS=1` enables non-production fallback embeddings only when `EDGE_ENV=dev`.
- In production, fallback embeddings are always disabled.

## Dependency Installation

```bash
cd apps/edge && poetry install && cd ../..
cd apps/desktop && npm install && cd ../..
cd apps/admin && npm install && cd ../..
```

Important:

- Do not activate unrelated virtualenvs before running `make` commands.
- `make dev-edge` always runs inside the Poetry-managed edge environment and performs a dependency preflight.

Cloud/Admin runtime is Docker-first (recommended beginner path). This avoids local Python version and dependency issues.

Local cloud development without Docker is optional and requires Python `3.11` to `3.13`.

## Cloud Local Dev Python Constraints (Optional Path)

Use this only when you intentionally run cloud outside Docker.

- Required interpreter range: Python `3.11` to `3.13`.
- Recommended quick setup on macOS with `pyenv`:

```bash
brew install pyenv
pyenv install 3.12.8
pyenv local 3.12.8
python --version
```

Then install cloud deps in `apps/cloud` and run migrations before startup.

## Cloud DB Migrations (Alembic)

Docker Compose path runs migrations automatically (`alembic upgrade head`) before cloud startup.

Manual commands (from `apps/cloud`):

```bash
alembic upgrade head
alembic revision --autogenerate -m "describe schema change"
```

If you use local cloud runtime without Docker, run `alembic upgrade head` before starting uvicorn.

## Recommended Local Run (3 Terminals)

Terminal 1: Cloud + Admin (Docker)

```bash
docker compose up --build
```

Terminal 2: Edge API (loopback-only)

```bash
make dev-edge
```

Terminal 3: Desktop app

```bash
make dev-desktop
```

## Quick Demo (One Command)

For portfolio/demo presentation path:

```bash
make demo
```

What `make demo` does:

- starts cloud/admin/postgres (`make demo-up`) and waits for health.
- launches desktop with demo-oriented env defaults (`make demo-desktop`).
- keeps local auth functional even if cloud telemetry is temporarily unavailable.
- `make demo` is interactive and blocks until desktop closes.
- expected demo close exits are `0` (normal close) and `130/143` (interrupt/terminate) by default.
- set `DEMO_AUTO_CLOSE_SECONDS=<n>` for scriptable desktop timeout-close in automation runs.

Demo controls:

```bash
make demo-checklist
make demo-verify
DEMO_VERIFY_DESKTOP=1 DEMO_VERIFY_DESKTOP_AUTO_CLOSE_SECONDS=20 make demo-verify
DEMO_AUTO_CLOSE_SECONDS=30 make demo-desktop
make demo-desktop-verify
make demo-down
make demo-down V=1
```

## Desktop UX (v2.5.0)

Primary tabs in the desktop UI:

- `Login`: live preview, challenge instructions, challenge progress, and explicit step-up handoff.
- `Enroll`: wizard (`Start -> Capture -> Commit`) with quality feedback mapped from reason codes.
- `Settings`: Demo Mode, telemetry status, outbox/DLQ counters, identity reset, support bundle generation.

Bottom status strip:

- Service status (`Running/Starting/Stopped`) with restart action when stopped.
- Camera status (`Ready/Error`).
- Last sync time from diagnostics telemetry fields.

Screenshot placeholders (capture and attach during release QA):

- `docs/images/desktop-login-placeholder.png`
- `docs/images/desktop-enroll-placeholder.png`
- `docs/images/desktop-settings-placeholder.png`

Optional preflight helpers:

```bash
make check-edge-preflight
make check-telemetry-transport
make check-tauri-config
```

## Health Checks

Edge exposes both process-level and API-level health endpoints:

```bash
curl http://127.0.0.1:8787/health
curl http://127.0.0.1:8787/api/v1/health
```

Use `/api/v1/health` for API-path checks and `/health` for basic process liveness.

Cloud/Admin checks:

```bash
curl http://127.0.0.1:8000/health
curl -H "X-Admin-Token: ${ADMIN_API_TOKEN}" http://127.0.0.1:8000/v1/admin/stats
curl http://127.0.0.1:3000
COOKIE_JAR="$(mktemp)"
curl -sS -c "${COOKIE_JAR}" -H "Content-Type: application/json" \
  -X POST \
  -d "{\"username\":\"${ADMIN_UI_USERNAME}\",\"password\":\"${ADMIN_UI_PASSWORD}\"}" \
  http://127.0.0.1:3000/api/admin/session/login >/dev/null
curl -b "${COOKIE_JAR}" http://127.0.0.1:3000/api/cloud/v1/admin/stats?window=24h
rm -f "${COOKIE_JAR}"
```

Admin UI routes:

- `http://127.0.0.1:3000/` Overview (cards + charts)
- `http://127.0.0.1:3000/events` Event exploration and detail drawer
- `http://127.0.0.1:3000/devices` Device reliability table and drill-down
- `http://127.0.0.1:3000/support` Support bundle generation/download

## Validation Commands

Tests:

```bash
make test-edge
make test-cloud
make test
```

Build checks:

```bash
make check-desktop-ts
make build-desktop-web
make check-desktop-rust
make docker-build
```

Smoke checks:

```bash
make smoke-edge
make smoke-cloud
make smoke-cloud-recovery
make smoke-admin
make smoke-desktop
make smoke-bundling
make check-invariants
make support-bundle
make check-local-support-bundle
make release-evidence
make pilot-evidence
```

Perf check:

```bash
make perf-edge
```

## One-Command Release Preflight

```bash
make release-check
RELEASE_EXPECT_TAG=vX.Y.Z make release-check
RUN_TELEMETRY_TRANSPORT_PREFLIGHT=1 make release-check
RELEASE_EXPECT_TAG=vX.Y.Z make check-release-tag
```

`make release-check` enforces:
- cloud and local support-bundle sanitization checks
- client bundle admin-token exposure checks
- tracked git status unchanged from start to finish
- optional live telemetry transport preflight when `RUN_TELEMETRY_TRANSPORT_PREFLIGHT=1`

Pilot readiness checklist: `docs/PILOT_FREEZE.md`.

## Packaging

```bash
make bundle-edge
make build-desktop
```

For detailed dependency installer logs during bundling, use:

```bash
BUNDLE_VERBOSE=1 make bundle-edge
```

Desktop warning budget check:

```bash
make check-desktop-warning-budget
```

Bundled local artifact ignored by git:

- `apps/desktop/resources/edge/pyvenv/`

## Distribution Build (Desktop)

Build flow:

```bash
make bundle-edge
make build-desktop
```

Where artifacts are generated:

- macOS bundles and installers: `apps/desktop/src-tauri/target/release/bundle/`

Mode behavior:

- Dev (`make dev-desktop`): desktop starts edge from source tree for fast iteration.
- Production bundle (`make build-desktop`): desktop starts bundled `apps/desktop/resources/edge/run_edge.sh` using bundled `pyvenv` (no Poetry required on target machine).

Distribution smoke:

```bash
./scripts/smoke_test_bundling.sh
```

Optional local sanity check for "no Poetry at runtime" path:

```bash
PATH="/usr/bin:/bin:/usr/sbin:/sbin" SKIP_DESKTOP_BUILD=1 ./scripts/smoke_test_bundling.sh
```

## Support Bundle (Sanitized)

Generate a support/debug bundle without raw frames, embeddings, tokens, or signatures:

```bash
EDGE_TOKEN="${EDGE_AUTH_TOKEN}" ADMIN_TOKEN="${ADMIN_API_TOKEN}" ./scripts/support_bundle.sh
./scripts/check_local_support_bundle_sanitization.sh
```

Artifact path:

- `scripts/support/out/support_bundle_<timestamp>.tar.gz`

Operator UI flow (recommended):

- Open `/support` in Admin UI.
- Click `Generate support bundle`.
- Downloaded file is generated by Cloud endpoint `POST /v1/admin/support-bundle` and sanitized server-side.

## CI Parity

CI enforces on PRs and `main` pushes:

- edge pytest
- cloud pytest
- desktop web build + cargo check
- docker compose build (cloud + admin)
- release parity gate (`make release-check` equivalent hardening path)

Workflow files:

- `.github/workflows/edge-tests.yml`
- `.github/workflows/cloud-tests.yml`
- `.github/workflows/desktop-build.yml`
- `.github/workflows/docker-build.yml`
- `.github/workflows/release-parity.yml`

## Release

Use `docs/RELEASE.md` for tag and release steps.

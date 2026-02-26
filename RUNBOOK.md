# SentinelID Runbook (v2.0.0)

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
- `NEXT_PUBLIC_ADMIN_TOKEN` (must match `ADMIN_API_TOKEN`)
- `NEXT_PUBLIC_CLOUD_BASE_URL` (`http://127.0.0.1:8000` for host-local runs; Docker sets `http://cloud:8000`)

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

Demo controls:

```bash
make demo-checklist
make demo-down
make demo-down V=1
```

## Desktop UX (v1.9.0)

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
curl http://127.0.0.1:3000/api/cloud/v1/admin/stats?window=24h
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
make support-bundle
```

Perf check:

```bash
make perf-edge
```

## One-Command Release Preflight

```bash
make release-check
```

## Packaging

```bash
make bundle-edge
make build-desktop
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

Workflow files:

- `.github/workflows/edge-tests.yml`
- `.github/workflows/cloud-tests.yml`
- `.github/workflows/desktop-build.yml`
- `.github/workflows/docker-build.yml`

## Release

Use `docs/RELEASE.md` for tag and release steps.

# SentinelID Runbook (v1.0.2)

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

## Dependency Installation

```bash
cd apps/edge && poetry install && cd ../..
cd apps/desktop && npm install && cd ../..
cd apps/admin && npm install && cd ../..
```

Cloud/Admin runtime is Docker-first (recommended). This avoids local Python version and dependency issues.

Local cloud development without Docker is optional and requires Python `3.11` to `3.13`.

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
```

## Validation Commands

Tests:

```bash
make test-edge
make test-cloud
make test
```

Build checks:

```bash
make build-desktop-web
make check-desktop-rust
make docker-build
```

Smoke checks:

```bash
make smoke-edge
make smoke-cloud
make smoke-admin
make smoke-desktop
make smoke-bundling
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

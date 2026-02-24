# SentinelID Runbook (v1.0.0)

This is the single source of truth for local run, validation, and release preflight commands.

## Prerequisites

- macOS or Linux
- Python 3.11+
- Poetry
- Node.js 18+
- Rust toolchain (Tauri)
- Docker + `docker compose`

## Environment

```bash
cp .env.example .env
```

Required values:

- `EDGE_AUTH_TOKEN`
- `ADMIN_API_TOKEN`
- `NEXT_PUBLIC_ADMIN_TOKEN` (match `ADMIN_API_TOKEN`)

## Dependency Installation

```bash
cd apps/edge && poetry install && cd ../..
cd apps/cloud && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt && cd ../..
cd apps/desktop && npm install && cd ../..
cd apps/admin && npm install && cd ../..
```

## One-Command Release Preflight

```bash
make release-check
```

This runs tests, desktop checks, docker builds, smoke scripts, and perf benchmark.

## Manual Run Path

### 1) Edge local

```bash
cd apps/edge
EDGE_ENV=dev EDGE_HOST=127.0.0.1 EDGE_PORT=8787 EDGE_AUTH_TOKEN=devtoken poetry run uvicorn sentinelid_edge.main:app --host 127.0.0.1 --port 8787
```

Health:

```bash
curl http://127.0.0.1:8787/api/v1/health
```

### 2) Cloud + Admin stack

```bash
docker compose up --build
```

Health:

```bash
curl http://127.0.0.1:8000/health
curl -H "X-Admin-Token: ${ADMIN_API_TOKEN}" http://127.0.0.1:8000/v1/admin/stats
```

### 3) Desktop dev

```bash
make dev-desktop
```

## Validation Commands

### Tests

```bash
make test-edge
make test-cloud
make test
```

### Desktop checks

```bash
make build-desktop-web
make check-desktop-rust
```

### Docker build checks

```bash
make docker-build
```

### Smoke checks

```bash
make smoke-edge
make smoke-cloud
make smoke-admin
make smoke-desktop
make smoke-bundling
```

### Perf check

```bash
make perf-edge
```

## Packaging

Bundle edge runtime and build desktop app:

```bash
make bundle-edge
make build-desktop
```

Bundled artifacts are reproducible locally and ignored via `.gitignore`:

- `apps/desktop/resources/edge/pyvenv/`

## CI Parity

CI enforces the same key checks on PRs and pushes to `main`:

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

Use `docs/RELEASE.md` for tagging rules and release cut steps.

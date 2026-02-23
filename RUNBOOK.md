# SentinelID Runbook

This is the authoritative operational guide for local setup, service startup, smoke checks, and testing.

## Prerequisites

- macOS or Linux
- Python 3.11+
- Poetry
- Node.js 18+
- Rust toolchain (for Tauri)
- Docker + Docker Compose plugin (`docker compose`)

## Setup

### 1) Clone and configure environment

```bash
git clone <repo-url>
cd SentinelID
cp .env.example .env
```

Set admin token values in `.env` (must match):

- `ADMIN_API_TOKEN`
- `NEXT_PUBLIC_ADMIN_TOKEN`

### 2) Install Edge dependencies (Poetry)

```bash
cd apps/edge
poetry install
cd ../..
```

### 3) Install Desktop dependencies

```bash
cd apps/desktop
npm install
cd ../..
```

### 4) Install Admin dependencies (optional for non-Docker local dev)

```bash
cd apps/admin
npm install
cd ../..
```

## Run Services

### Edge dev (FastAPI)

```bash
cd apps/edge
EDGE_ENV=dev EDGE_AUTH_TOKEN=devtoken poetry run uvicorn sentinelid_edge.main:app --reload --host 127.0.0.1 --port 8787
```

Health check:

```bash
curl http://127.0.0.1:8787/health
curl http://127.0.0.1:8787/api/v1/
```

### Desktop dev (Tauri)

From repo root:

```bash
make dev-desktop
```

Equivalent direct command:

```bash
cd apps/desktop
npm run tauri dev
```

### Cloud/Admin (Docker Compose)

SentinelID uses `docker-compose.yml` at repo root.

```bash
docker compose up --build
```

Health checks:

```bash
curl http://127.0.0.1:8000/health
curl -H "X-Admin-Token: ${ADMIN_API_TOKEN:-dev-admin-token}" http://127.0.0.1:8000/v1/admin/stats
```

## Smoke Tests

### Admin API smoke test

```bash
API_URL=http://127.0.0.1:8000 ADMIN_TOKEN=${ADMIN_API_TOKEN:-dev-admin-token} ./scripts/smoke_test_admin.sh
```

### Desktop bundling smoke test

```bash
./scripts/bundle_edge_venv.sh
./scripts/smoke_test_bundling.sh
```

### Eval smoke run

Use the running edge URL and bearer token:

```bash
./scripts/eval/run_eval.sh http://127.0.0.1:8787 devtoken 6
```

Output is written to `scripts/eval/out/`.

## Tests

### Full suite

```bash
make test
```

### Edge tests

```bash
cd apps/edge
poetry run pytest -v
```

### Cloud tests

```bash
cd apps/cloud
pytest -v
```

### Admin lint/build checks

```bash
cd apps/admin
npm run lint
npm run build
```

### Desktop build check

```bash
cd apps/desktop
npm run tauri build
```

## Utility Scripts

- `scripts/bundle_edge_venv.sh`: Builds desktop-embedded edge runtime venv under `apps/desktop/resources/edge/`.
- `scripts/smoke_test_bundling.sh`: Verifies bundled runtime artifacts.
- `scripts/smoke_test_admin.sh`: Verifies `/v1/admin/devices`, `/v1/admin/events`, `/v1/admin/stats` and auth behavior.
- `scripts/eval/run_eval.sh`: Runs repeated auth attempts and writes sanitized evaluation JSON.
- `scripts/gen_types.sh`: Placeholder for OpenAPI-to-TypeScript type generation.
- `scripts/dev_cert.sh`: Placeholder (currently empty; no-op).

## Troubleshooting

### Port already in use

```bash
lsof -nP -iTCP:8787 -sTCP:LISTEN
lsof -nP -iTCP:8000 -sTCP:LISTEN
lsof -nP -iTCP:3000 -sTCP:LISTEN
```

Kill a conflicting process:

```bash
kill -9 <pid>
```

### Reset edge local DB and keys

```bash
rm -rf apps/edge/.sentinelid
```

### Reset Docker state (cloud/admin/postgres)

```bash
docker compose down -v
docker compose up --build
```

### Force Docker rebuild without cache

```bash
docker compose build --no-cache
docker compose up
```

### Admin 401 errors

Ensure token values match:

- `ADMIN_API_TOKEN` (cloud)
- `NEXT_PUBLIC_ADMIN_TOKEN` (admin UI)
- `ADMIN_TOKEN` used by smoke test scripts

### Bundling or Tauri build failures

```bash
make clean
make bundle-edge
make build-desktop
```

### Tag mismatch or stale local tags during release checks

```bash
git fetch --tags --force
git tag
# if needed:
# git tag -d <tag>
# git fetch origin tag <tag>
```

## Durable References

- System architecture: `docs/architecture.md`
- API reference: `docs/api.md`
- Privacy: `docs/privacy.md`
- Threat model: `docs/threat-model.md`
- Evaluation: `docs/evaluation.md`
- Packaging: `docs/PACKAGING.md`
- Recovery: `docs/RECOVERY.md`
- Key management: `docs/KEY_MANAGEMENT.md`
- Release history: `CHANGELOG.md`

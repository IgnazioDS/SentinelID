# SentinelID Runbook

This is the single authoritative local run path for SentinelID v0.9.

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
- `NEXT_PUBLIC_ADMIN_TOKEN` (should match `ADMIN_API_TOKEN`)

## Install Dependencies

```bash
cd apps/edge && poetry install && cd ../..
cd apps/desktop && npm install && cd ../..
cd apps/admin && npm install && cd ../..
```

## Start Services

### 1) Edge (local)

```bash
cd apps/edge
EDGE_ENV=dev EDGE_HOST=127.0.0.1 EDGE_PORT=8787 EDGE_AUTH_TOKEN=devtoken poetry run uvicorn sentinelid_edge.main:app --host 127.0.0.1 --port 8787
```

Health checks:

```bash
curl http://127.0.0.1:8787/health
curl http://127.0.0.1:8787/api/v1/health
```

### 2) Cloud + Admin stack

```bash
docker compose up --build
```

Health checks:

```bash
curl http://127.0.0.1:8000/health
curl -H "X-Admin-Token: ${ADMIN_API_TOKEN}" http://127.0.0.1:8000/v1/admin/stats
```

### 3) Desktop app (dev)

```bash
cd apps/desktop
npm run tauri dev
```

## Smoke Tests

### Edge auth smoke

```bash
EDGE_URL=http://127.0.0.1:8787 EDGE_TOKEN=devtoken ./scripts/smoke_test_edge.sh
```

### Cloud ingest + admin smoke

```bash
CLOUD_URL=http://127.0.0.1:8000 ADMIN_TOKEN=${ADMIN_API_TOKEN} ./scripts/smoke_test_cloud.sh
```

### Desktop launcher smoke (bundled `run_edge.sh`)

```bash
./scripts/smoke_test_desktop.sh
```

### Full desktop bundle + smoke

```bash
./scripts/build_and_smoke_desktop.sh
```

## Performance Check

```bash
python3 scripts/perf/bench_edge.py --base-url http://127.0.0.1:8787 --token devtoken --attempts 8 --frames 12
```

Optional output file:

```bash
python3 scripts/perf/bench_edge.py --out scripts/eval/out/bench_edge.json
```

## Tests

```bash
cd apps/edge && poetry run pytest
cd ../cloud && pytest
cd ../admin && npm run build
```

## Release Workflow Reference

For build/release tagging steps, use `docs/RELEASE.md`.


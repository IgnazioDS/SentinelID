# Release Guide (v0.9)

## 1) Build Desktop Bundle

```bash
./scripts/bundle_edge_venv.sh
cd apps/desktop
npm run tauri build
cd ../..
```

Or run the combined path:

```bash
./scripts/build_and_smoke_desktop.sh
```

## 2) Run Smoke Tests

Edge:

```bash
EDGE_URL=http://127.0.0.1:8787 EDGE_TOKEN=devtoken ./scripts/smoke_test_edge.sh
```

Cloud:

```bash
CLOUD_URL=http://127.0.0.1:8000 ADMIN_TOKEN=${ADMIN_API_TOKEN} ./scripts/smoke_test_cloud.sh
```

Desktop launcher:

```bash
./scripts/smoke_test_desktop.sh
```

## 3) Run Performance Benchmark

```bash
python3 scripts/perf/bench_edge.py --base-url http://127.0.0.1:8787 --token devtoken --attempts 8 --frames 12
```

## 4) Run Test Suites

```bash
cd apps/edge && poetry run pytest && cd ../..
cd apps/cloud && pytest && cd ../..
```

## 5) Tagging Checklist

Example release commands:

```bash
git switch main
git pull
git tag -a v0.9.0 -m "SentinelID v0.9.0 release candidate"
git push origin v0.9.0
git show --no-patch --decorate v0.9.0
```

For pre-release tags:

```bash
git tag -a v0.9.0-alpha.1 -m "SentinelID v0.9.0-alpha.1"
git push origin v0.9.0-alpha.1
```


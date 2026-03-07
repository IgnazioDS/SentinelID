# Desktop Packaging (v2.4.0)

For environment setup and baseline run commands, use `RUNBOOK.md`.

For presenter-facing scripted walkthrough, use `docs/DEMO_CHECKLIST.md`.

For admin auth configuration, prefer `ADMIN_UI_PASSWORD_HASH_B64` in Docker Compose and keep direct bcrypt hashes single-quoted in `.env` when `ADMIN_UI_PASSWORD_HASH` is used.

## Purpose

SentinelID desktop packaging bundles the edge runtime into the Tauri application so production builds do not depend on Poetry or source-tree edge startup.

## Bundled Layout

Bundling creates the following under `apps/desktop/resources/edge/`:

- `pyvenv_active/`: Python virtual environment with edge dependencies plus `uvicorn`.
- `run_edge.sh`: launcher used by the Tauri runtime in production mode.
- `app/sentinelid_edge/`: bundled source fallback for `PYTHONPATH` startup safety.

## Standard Workflow

From repo root:

```bash
make bundle-edge
make build-desktop
```

Equivalent one-shot script:

```bash
./scripts/build_and_smoke_desktop.sh
```

Validation:

```bash
./scripts/smoke_test_bundling.sh
./scripts/smoke_test_desktop.sh
```

Demo runtime helpers:

```bash
make demo-up
make demo-desktop
make demo-verify
make demo-down
```

## Clean-Machine Runtime Verification

Distribution smoke verifies the bundled edge runtime directly (without Poetry):

```bash
./scripts/smoke_test_bundling.sh
```

What it validates:

- bundled runner exists and is executable
- bundled `pyvenv_active` contains required runtime packages
- edge starts on a dynamic loopback port using bundled runtime
- `/health` and `/api/v1/health` return success
- protected endpoint rejects unauthenticated access with `401`

## Runtime Behavior

### Development mode

- `make dev-desktop` starts Tauri dev mode.
- Tauri runs edge from source (`apps/edge`) via `python -m uvicorn`.

### Production mode

- Tauri resolves `resources/edge/run_edge.sh`.
- Launcher activates bundled `pyvenv_active` (or legacy `pyvenv`) and starts edge.
- Desktop assigns a loopback host, runtime port, and bearer token.

## Expected Inputs

- Python 3.11+
- Node.js and Rust toolchain for Tauri
- Edge dependencies resolvable from `apps/edge/pyproject.toml` / `poetry.lock`

## Common Failures

### Missing bundled venv

```bash
rm -rf apps/desktop/resources/edge/pyvenv_active apps/desktop/resources/edge/pyvenv
make bundle-edge
```

### Uvicorn unavailable in bundle

```bash
apps/desktop/resources/edge/pyvenv_active/bin/python -m uvicorn --version
./scripts/bundle_edge_venv.sh
```

### Build artifacts need reset

```bash
make clean
make bundle-edge
make build-desktop
```

### macOS Gatekeeper warnings on unsigned local bundles

For local-only testing, remove quarantine attributes before launching:

```bash
xattr -dr com.apple.quarantine apps/desktop/src-tauri/target/release/bundle
```

### Runner permission error

```bash
chmod +x apps/desktop/resources/edge/run_edge.sh
```

### Port conflict

The desktop launcher uses a dynamic free port, but direct local tests can still conflict. Re-run the smoke script or set a different `EDGE_PORT`.

## Related Docs

- Recovery guide: `docs/RECOVERY.md`
- Key management: `docs/KEY_MANAGEMENT.md`

# Desktop Packaging

For environment setup and baseline run commands, use `RUNBOOK.md`.

## Purpose

SentinelID desktop packaging bundles the edge runtime into the Tauri application so production builds do not depend on a system Python installation.

## Packaging Artifacts

Bundling creates the following under `apps/desktop/resources/edge/`:

- `pyvenv/`: Python virtual environment with edge dependencies.
- `run_edge.sh`: launcher used by the Tauri runtime in production mode.

## Standard Workflow

From repo root:

```bash
make bundle-edge
make build-desktop
```

Validation:

```bash
./scripts/smoke_test_bundling.sh
```

## Runtime Behavior

### Development mode

- `make dev-desktop` starts Tauri dev mode.
- Tauri runs edge from source (`apps/edge`) via `python -m uvicorn`.

### Production mode

- Tauri resolves `resources/edge/run_edge.sh`.
- Launcher activates bundled `pyvenv` and starts edge.
- Desktop assigns a loopback host, runtime port, and bearer token.

## Expected Inputs

- Python 3.11+
- Node.js and Rust toolchain for Tauri
- Edge dependencies resolvable from `apps/edge/pyproject.toml` / `poetry.lock`

## Common Failures

### Missing bundled venv

```bash
rm -rf apps/desktop/resources/edge/pyvenv
make bundle-edge
```

### Uvicorn unavailable in bundle

```bash
apps/desktop/resources/edge/pyvenv/bin/python -m uvicorn --version
./scripts/bundle_edge_venv.sh
```

### Build artifacts need reset

```bash
make clean
make bundle-edge
make build-desktop
```

## Related Docs

- Recovery guide: `docs/RECOVERY.md`
- Key management: `docs/KEY_MANAGEMENT.md`

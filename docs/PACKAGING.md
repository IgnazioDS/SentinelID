# SentinelID Desktop Packaging Guide (Phase 5)

## Overview

Phase 5 enables self-contained desktop application packaging using Tauri with bundled Python runtime. The `bundle_edge_venv.sh` script creates a portable Python environment with all edge service dependencies.

## Prerequisites

- Python 3.11+
- Node.js 18+
- Rust (for Tauri)
- Poetry (optional, for dependency resolution)

## Bundling Process

### Step 1: Prepare for Bundling

Before building the Tauri application, you must bundle the edge runtime.

```bash
# Navigate to project root
cd /path/to/SentinelID

# Run the bundling script
./scripts/bundle_edge_venv.sh
```

Expected output:
```
🔨 Bundling Edge Runtime for Tauri Desktop App
   Project Root: /path/to/SentinelID
   Resources Dir: /path/to/SentinelID/apps/desktop/resources/edge
...
✅ Bundle complete!
   Venv location: /path/to/SentinelID/apps/desktop/resources/edge/pyvenv
   Launcher location: /path/to/SentinelID/apps/desktop/resources/edge/run_edge.sh
```

### Step 2: Verify Resources Created

```bash
# Check that resources were created
ls -la apps/desktop/resources/edge/

# Should contain:
# - pyvenv/       (Python virtual environment)
# - run_edge.sh   (Launcher script)
```

### Step 3: Build Tauri Application

```bash
cd apps/desktop

# Development build (uses source uvicorn)
npm run tauri dev

# Production build (uses bundled venv)
npm run tauri build
```

### Step 4: Distribution

The compiled Tauri application includes:
- All edge service dependencies in bundled venv
- Run_edge.sh launcher that spawns the edge service
- Desktop UI with embedded web view
- Integrated cross-platform package

## Architecture

### Directory Structure

```
apps/desktop/
├── src/                  # Frontend UI components
├── src-tauri/            # Tauri Rust code
│   ├── src/
│   │   └── main.rs      # Edge launcher (dev/prod modes)
│   └── tauri.conf.json  # Tauri configuration
├── resources/
│   └── edge/
│       ├── pyvenv/      # Bundled Python venv
│       │   ├── bin/
│       │   │   ├── python
│       │   │   ├── pip
│       │   │   └── uvicorn
│       │   ├── lib/
│       │   └── include/
│       └── run_edge.sh  # Launcher script
└── dist/               # Built frontend (generated)
```

### Launcher Behavior

**Development Mode** (`npm run tauri dev`):
- Runs `python -m uvicorn sentinelid_edge.main:app` from ./apps/edge
- Uses system Python with poetry-managed dependencies
- Hot reload enabled
- Direct import paths

**Production Mode** (`npm run tauri build`):
- Uses bundled `run_edge.sh` from resources/edge/
- Isolated venv with vendored dependencies
- No system Python required
- Self-contained application

### Port and Token Management

The Tauri launcher:
1. Selects random free port (8000-9000)
2. Generates UUID-based auth token
3. Passes both to edge process via environment
4. Polls `/api/v1/` health endpoint until ready
5. Stores edge info in application state
6. Exposes edge via `http://127.0.0.1:{port}` with token auth

## Advanced Configuration

### Custom Venv Location

To use a custom venv location:

```bash
# Set venv path before building
export SENTINELID_VENV_PATH=/custom/path

./scripts/bundle_edge_venv.sh
```

### Python Version Specific Bundling

The script detects Python 3.11+ automatically. To use specific version:

```bash
# Use specific Python version
python3.11 -m venv apps/desktop/resources/edge/pyvenv
```

### Dependency Updates

To update bundled dependencies:

```bash
# Update apps/edge/pyproject.toml with new versions
# Then re-run bundle script
./scripts/bundle_edge_venv.sh
```

## Troubleshooting

### Venv Not Found After Bundling

```bash
# Verify resources directory
ls apps/desktop/resources/edge/pyvenv/bin/python

# Check bundle script output for errors
./scripts/bundle_edge_venv.sh 2>&1 | tee bundle.log
```

### Uvicorn Import Errors

```bash
# Verify uvicorn in venv
apps/desktop/resources/edge/pyvenv/bin/python -m pip list | grep uvicorn

# Reinstall if missing
./scripts/bundle_edge_venv.sh
```

### Port Conflicts

The launcher selects random ports in range 8000-9000. If conflicts occur:

```bash
# Check occupied ports
lsof -i :8000-8100

# Kill conflicting process
kill -9 <PID>
```

### Cross-Platform Path Issues

The run_edge.sh script uses bash. For Windows development:

```bash
# Ensure Git Bash or WSL is available
# tauri.conf.json includes platform-specific settings
```

## Deployment Considerations

### Signing and Notarization

For macOS app store distribution:

```bash
# Configure in tauri.conf.json
"bundle": {
  "macOS": {
    "signingIdentity": "Your Developer Identity"
  }
}
```

### Size Optimization

The bundled venv is ~500MB (depends on dependencies).

To reduce:
1. Remove dev dependencies before bundling
2. Strip debug symbols from Python binaries
3. Use UPX compression on final binary

### Update Strategy

For app updates:

```bash
# Option 1: Tauri built-in updater
# Requires github releases configured in tauri.conf.json

# Option 2: Download installer
# Manual distribution of new bundles
```

## Version Information

- Tauri version: v1.x (check package.json)
- Python bundled: 3.11+
- Edge service: 0.5.0
- Configuration: apps/desktop/src-tauri/tauri.conf.json v0.5.0

## Next Steps

- Implement Tauri auto-updater for OTA updates
- Add cryptographic signing for binary verification
- Configure CI/CD for multi-platform builds
- Set up notarization for macOS

See RECOVERY.md for disaster recovery procedures.

#!/bin/bash
# Edge runtime launcher script
# Called by Tauri in production builds

# Get script directory (should be resources/edge)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/pyvenv"

# Extract parameters from command line or environment
PORT=${1:-${EDGE_PORT:-8000}}
HOST=${2:-${EDGE_HOST:-127.0.0.1}}
TOKEN=${3:-${EDGE_AUTH_TOKEN:-dev-token}}

# Ensure runtime settings are visible to the app config loader.
export EDGE_PORT="$PORT"
export EDGE_HOST="$HOST"
export EDGE_AUTH_TOKEN="$TOKEN"

# Activate venv and start uvicorn
source "$VENV_DIR/bin/activate"
exec python -m uvicorn sentinelid_edge.main:app \
    --host "$HOST" \
    --port "$PORT" \
    --no-access-log \
    --log-level info

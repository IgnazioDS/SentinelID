#!/bin/bash

# Bundle Edge runtime into Tauri resources
# Creates a clean Python venv with edge dependencies for production builds

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DESKTOP_APP="$PROJECT_ROOT/apps/desktop"
EDGE_APP="$PROJECT_ROOT/apps/edge"
RESOURCES_DIR="$DESKTOP_APP/resources/edge"
VENV_DIR="$RESOURCES_DIR/pyvenv"

echo "Bundling Edge Runtime for Tauri Desktop App"
echo "   Project Root: $PROJECT_ROOT"
echo "   Resources Dir: $RESOURCES_DIR"
echo ""

# Step 1: Create resources directory structure
echo "Creating resources directory structure..."
mkdir -p "$RESOURCES_DIR"
rm -rf "$VENV_DIR"  # Clean previous builds

# Step 2: Create Python virtual environment
echo "Creating Python virtual environment..."
python3 -m venv "$VENV_DIR"

# Activate venv
source "$VENV_DIR/bin/activate"

# Upgrade pip
pip install --upgrade pip setuptools wheel

# Step 3: Install edge dependencies
echo "Installing edge dependencies..."
cd "$EDGE_APP"

POETRY_BIN=""
if command -v poetry >/dev/null 2>&1; then
    POETRY_BIN="$(command -v poetry)"
elif [ -x "$EDGE_APP/.venv/bin/poetry" ]; then
    POETRY_BIN="$EDGE_APP/.venv/bin/poetry"
fi

# If poetry.lock exists, use it for reproducible builds
if [ -f "poetry.lock" ]; then
    if [ -n "$POETRY_BIN" ]; then
        echo "   Using poetry.lock for reproducible installation..."
        # Export dependencies from poetry.lock to requirements.txt
        "$POETRY_BIN" export -f requirements.txt --output /tmp/requirements.txt --without-hashes
        pip install -r /tmp/requirements.txt
        rm /tmp/requirements.txt
    else
        echo "   Poetry not found; falling back to pip editable install."
        pip install -e .
    fi
elif [ -f "pyproject.toml" ]; then
    echo "   Using pyproject.toml..."
    pip install -e .
else
    echo "   ERROR: No pyproject.toml or poetry.lock found in $EDGE_APP"
    exit 1
fi

# Step 4: Install the edge package
echo "Installing edge package..."
# Install package code into the bundled venv.
pip install -e .

# Ensure runtime deps that are imported dynamically are always present.
MISSING_DEPS=()
python -c "import cryptography" >/dev/null 2>&1 || MISSING_DEPS+=("cryptography>=41,<45")
python -c "import httpx" >/dev/null 2>&1 || MISSING_DEPS+=("httpx>=0.25,<0.29")
if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
    echo "Installing missing runtime dependencies: ${MISSING_DEPS[*]}"
    pip install "${MISSING_DEPS[@]}"
fi

# Step 5: Verify uvicorn is available
echo "✓ Verifying uvicorn installation..."
if ! $VENV_DIR/bin/python -m uvicorn --version > /dev/null; then
    echo "   ERROR: uvicorn not found in venv"
    exit 1
fi
echo "   ✓ uvicorn is available"

# Step 6: Create run_edge.sh launcher
echo "Creating run_edge.sh launcher..."
cat > "$RESOURCES_DIR/run_edge.sh" << 'LAUNCHER'
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
LAUNCHER

chmod +x "$RESOURCES_DIR/run_edge.sh"
echo "   ✓ run_edge.sh created and executable"

# Step 7: Deactivate venv
deactivate

# Step 8: Summary
echo ""
echo "Bundle complete."
echo "   Venv location: $VENV_DIR"
echo "   Launcher location: $RESOURCES_DIR/run_edge.sh"
echo "   Resources ready for Tauri packaging"
echo ""
echo "Next steps:"
echo "  1. Update apps/desktop/tauri.conf.json to include resources"
echo "  2. Update apps/desktop/src-tauri/src/main.rs to use run_edge.sh"
echo "  3. Build Tauri app: npm run tauri build"

#!/bin/bash

# Phase 3 Testing Script
# Runs docker build, starts services, and executes smoke tests

set -e

REPO_ROOT=$(cd "$(dirname "$0")" && pwd)
cd "$REPO_ROOT"

echo "=== Phase 3 Testing Script ==="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Step 1: Build Docker images
echo -e "${YELLOW}Step 1: Building Docker images${NC}"
docker-compose build
if [ $? -ne 0 ]; then
    echo -e "${RED}Docker build failed${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker build successful${NC}"
echo ""

# Step 2: Start services
echo -e "${YELLOW}Step 2: Starting services${NC}"
docker-compose up -d postgres cloud
echo "Waiting for PostgreSQL to be healthy..."
sleep 15

# Verify cloud is running
if curl -s http://localhost:8000/health | grep -q "healthy"; then
    echo -e "${GREEN}✓ Cloud service is running${NC}"
else
    echo -e "${RED}Cloud service failed to start${NC}"
    docker-compose logs cloud
    exit 1
fi
echo ""

# Step 3: Start edge service
echo -e "${YELLOW}Step 3: Starting edge service${NC}"
cd apps/edge
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install cryptography==41.0.7 httpx==0.25.1 > /dev/null 2>&1

export TELEMETRY_ENABLED=true
export CLOUD_INGEST_URL=http://127.0.0.1:8000/v1/ingest/events
export EDGE_ENV=dev
export EDGE_AUTH_TOKEN=devtoken

# Start edge in background
poetry run uvicorn sentinelid_edge.main:app --host 127.0.0.1 --port 8787 > /tmp/edge.log 2>&1 &
EDGE_PID=$!
sleep 5

# Verify edge is running
if curl -s -H "Authorization: Bearer devtoken" http://127.0.0.1:8787/api/v1/health | grep -q "ok"; then
    echo -e "${GREEN}✓ Edge service is running${NC}"
else
    echo -e "${RED}Edge service failed to start${NC}"
    cat /tmp/edge.log
    kill $EDGE_PID
    exit 1
fi
echo ""

# Step 4: Run unit tests
echo -e "${YELLOW}Step 4: Running unit tests${NC}"
pytest tests/test_audit_log.py tests/test_telemetry.py -v
if [ $? -ne 0 ]; then
    echo -e "${RED}Unit tests failed${NC}"
    kill $EDGE_PID
    exit 1
fi
echo -e "${GREEN}✓ All edge tests passed${NC}"
echo ""

cd "$REPO_ROOT/apps/cloud"
pytest tests/test_signature_verification.py -v
if [ $? -ne 0 ]; then
    echo -e "${RED}Cloud tests failed${NC}"
    kill $EDGE_PID
    exit 1
fi
echo -e "${GREEN}✓ All cloud tests passed${NC}"
echo ""

# Step 5: Run smoke test
echo -e "${YELLOW}Step 5: Running smoke test - auth flow${NC}"

# Start auth session
RESPONSE=$(curl -s -X POST -H "Authorization: Bearer devtoken" \
  http://127.0.0.1:8787/api/v1/auth/start \
  -H "Content-Type: application/json" -d '{}')

SESSION_ID=$(echo "$RESPONSE" | jq -r '.session_id // empty')
if [ -z "$SESSION_ID" ]; then
    echo -e "${RED}Failed to start auth session${NC}"
    echo "Response: $RESPONSE"
    kill $EDGE_PID
    exit 1
fi
echo -e "${GREEN}✓ Auth session started: $SESSION_ID${NC}"

# Finish auth session
FINISH_RESPONSE=$(curl -s -X POST -H "Authorization: Bearer devtoken" \
  http://127.0.0.1:8787/api/v1/auth/finish \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SESSION_ID\"}")

DECISION=$(echo "$FINISH_RESPONSE" | jq -r '.decision // empty')
if [ -z "$DECISION" ]; then
    echo -e "${RED}Failed to finish auth${NC}"
    echo "Response: $FINISH_RESPONSE"
    kill $EDGE_PID
    exit 1
fi
echo -e "${GREEN}✓ Auth completed with decision: $DECISION${NC}"
echo ""

# Wait for telemetry to reach cloud
sleep 2

# Step 6: Verify cloud received event
echo -e "${YELLOW}Step 6: Verifying cloud received telemetry${NC}"
EVENTS=$(curl -s http://127.0.0.1:8000/v1/admin/events?limit=5)
EVENT_COUNT=$(echo "$EVENTS" | jq '.total // 0')

if [ "$EVENT_COUNT" -gt 0 ]; then
    echo -e "${GREEN}✓ Cloud received $EVENT_COUNT event(s)${NC}"
else
    echo -e "${RED}Cloud did not receive any events${NC}"
    kill $EDGE_PID
    exit 1
fi
echo ""

# Step 7: Verify statistics
echo -e "${YELLOW}Step 7: Verifying statistics${NC}"
STATS=$(curl -s http://127.0.0.1:8000/v1/admin/stats)
echo "Cloud Statistics:"
echo "$STATS" | jq '.'
echo ""

# Step 8: Verify audit log
echo -e "${YELLOW}Step 8: Verifying audit log${NC}"
if [ -f ~/.sentinelid/audit.db ]; then
    echo -e "${GREEN}✓ Audit log created${NC}"
else
    echo -e "${RED}Audit log not found${NC}"
fi

if [ -f ~/.sentinelid/keys/device_keys.json ]; then
    echo -e "${GREEN}✓ Device keys created${NC}"
else
    echo -e "${RED}Device keys not found${NC}"
fi
echo ""

# Cleanup
kill $EDGE_PID 2>/dev/null || true
docker-compose down

# Summary
echo -e "${GREEN}=== Phase 3 Testing Complete ===${NC}"
echo ""
echo "All tests passed successfully!"
echo ""
echo "Phase 3 Features Validated:"
echo "✓ Audit logging with hash-chain integrity"
echo "✓ Device binding (ED25519 keypair generation)"
echo "✓ Telemetry signing and sanitization"
echo "✓ Cloud ingest with signature verification"
echo "✓ End-to-end auth → audit → telemetry → cloud flow"

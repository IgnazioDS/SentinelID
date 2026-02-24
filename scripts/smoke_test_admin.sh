#!/bin/bash

# SentinelID Admin Dashboard Smoke Tests
# Verify all admin API endpoints are accessible and return proper responses

set -e

# Configuration
API_URL="${API_URL:-http://localhost:8000}"
ADMIN_TOKEN="${ADMIN_TOKEN:-dev-admin-token}"
TIMEOUT=5

echo "Starting Admin Dashboard Smoke Tests"
echo "   API URL: $API_URL"
echo "   Timeout: ${TIMEOUT}s"
echo ""

# Test admin devices endpoint
echo "Testing /v1/admin/devices..."
response=$(curl -s -w "\n%{http_code}" \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  --max-time "$TIMEOUT" \
  "$API_URL/v1/admin/devices?limit=5")

status=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')

if [ "$status" = "200" ]; then
  device_count=$(echo "$body" | grep -o '"device_id"' | wc -l)
  echo "   ✓ Status: 200 OK (Found $device_count devices)"
else
  echo "   ✗ Status: $status (Expected 200)"
  exit 1
fi

# Test admin events endpoint
echo "Testing /v1/admin/events..."
response=$(curl -s -w "\n%{http_code}" \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  --max-time "$TIMEOUT" \
  "$API_URL/v1/admin/events?limit=5")

status=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')

if [ "$status" = "200" ]; then
  event_count=$(echo "$body" | grep -o '"event_id"' | wc -l)
  echo "   ✓ Status: 200 OK (Found $event_count events)"
else
  echo "   ✗ Status: $status (Expected 200)"
  exit 1
fi

# Test admin stats endpoint
echo "Testing /v1/admin/stats..."
response=$(curl -s -w "\n%{http_code}" \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  --max-time "$TIMEOUT" \
  "$API_URL/v1/admin/stats")

status=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')

if [ "$status" = "200" ]; then
  total_devices=$(echo "$body" | grep -o '"total_devices":[0-9]*' | cut -d: -f2)
  liveness_rate=$(echo "$body" | grep -o '"liveness_failure_rate":[0-9.]*' | cut -d: -f2)
  echo "   ✓ Status: 200 OK"
  echo "     - Total devices: $total_devices"
  echo "     - Liveness failure rate: $liveness_rate%"
else
  echo "   ✗ Status: $status (Expected 200)"
  exit 1
fi

# Test authentication rejection
echo "Testing authentication rejection (missing token)..."
response=$(curl -s -w "\n%{http_code}" \
  --max-time "$TIMEOUT" \
  "$API_URL/v1/admin/devices")

status=$(echo "$response" | tail -n1)

if [ "$status" = "401" ]; then
  echo "   ✓ Correctly returned 401 (Unauthorized)"
else
  echo "   ✗ Status: $status (Expected 401)"
  exit 1
fi

# Test invalid token rejection
echo "Testing authentication rejection (invalid token)..."
response=$(curl -s -w "\n%{http_code}" \
  -H "X-Admin-Token: invalid-token" \
  --max-time "$TIMEOUT" \
  "$API_URL/v1/admin/devices")

status=$(echo "$response" | tail -n1)

if [ "$status" = "401" ]; then
  echo "   ✓ Correctly returned 401 (Unauthorized)"
else
  echo "   ✗ Status: $status (Expected 401)"
  exit 1
fi

echo ""
echo "All smoke tests passed."

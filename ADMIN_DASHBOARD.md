# SentinelID Admin Dashboard (Phase 4)

## Overview

The Admin Dashboard (v0.4.0) provides authenticated access to monitoring and analytics for registered devices and authentication events.

## Features

### Events Page (`/events`)
- Real-time table of authentication events
- **Filters:**
  - Device ID: Filter events by specific device
  - Outcome: Filter by allow/deny/error status
- **Pagination:** Configurable page size (25/50/100 items)
- **Columns:**
  - Event ID (truncated to 8 chars)
  - Device ID
  - Outcome (color-coded badges: green=allow, red=deny, gray=error)
  - Liveness Status
  - Timestamp

### Statistics Page (`/stats`)
- Service-wide metrics and quality indicators
- **Metrics:**
  - Total devices registered
  - Active devices (last_seen within 24 hours)
  - Total events processed
  - Allow rate (successful authentications)
  - Deny rate (failed authentications)
  - Error rate (processing errors)
  - Liveness failure rate (failed liveness checks)

### Devices Page (`/devices`)
- List of registered devices
- **Columns:**
  - Device ID
  - Status (active/inactive badge)
  - Last Seen (timestamp)
  - Registered At (timestamp)
  - Event Count (number of events from device)
- **Pagination:** Configurable page size (25/50/100 items)

## Authentication

All admin API endpoints require the `X-Admin-Token` header:

```bash
curl -H "X-Admin-Token: your-admin-token" http://localhost:8000/v1/admin/devices
```

## Configuration

### Environment Variables

```bash
# Cloud Service
ADMIN_API_TOKEN=your-secure-token

# Admin UI
NEXT_PUBLIC_ADMIN_TOKEN=your-secure-token
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### Docker Compose

Service health checks and startup dependencies are configured in `docker-compose.yml`:

```yaml
cloud:
  environment:
    - ADMIN_API_TOKEN=${ADMIN_API_TOKEN:-dev-admin-token}
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8000/health"]

admin:
  depends_on:
    cloud:
      condition: service_healthy
  environment:
    - NEXT_PUBLIC_ADMIN_TOKEN=${NEXT_PUBLIC_ADMIN_TOKEN:-dev-admin-token}
```

## API Endpoints

All endpoints require `X-Admin-Token` header.

### GET /v1/admin/devices
List registered devices with pagination.

**Parameters:**
- `limit` (optional): Items per page (default: 50)
- `offset` (optional): Pagination offset (default: 0)

**Response:**
```json
{
  "devices": [
    {
      "device_id": "abc123",
      "registered_at": "2026-02-22T10:00:00",
      "last_seen": "2026-02-22T15:30:00",
      "is_active": true,
      "event_count": 42
    }
  ],
  "total": 150
}
```

### GET /v1/admin/events
List authentication events with filtering and pagination.

**Parameters:**
- `limit` (optional): Items per page (default: 50)
- `offset` (optional): Pagination offset (default: 0)
- `device_id` (optional): Filter by device ID
- `outcome` (optional): Filter by outcome (allow/deny/error)

**Response:**
```json
{
  "events": [
    {
      "event_id": "evt-123",
      "device_id": "abc123",
      "outcome": "allow",
      "liveness_passed": true,
      "timestamp": "2026-02-22T15:30:00"
    }
  ],
  "total": 5000
}
```

### GET /v1/admin/stats
Retrieve service statistics and quality metrics.

**Response:**
```json
{
  "total_devices": 150,
  "active_devices": 128,
  "total_events": 5000,
  "allow_count": 4500,
  "deny_count": 450,
  "error_count": 50,
  "liveness_failure_rate": 9.0
}
```

## Development

### Local Setup

1. Copy `.env.example` to `.env` and configure tokens
2. Start services: `docker-compose up --build`
3. Access admin dashboard at `http://localhost:3000`
4. Cloud API at `http://localhost:8000`

### Admin UI Architecture

- **Framework:** Next.js 14 with TypeScript
- **Client Library:** `lib/api.ts` - Typed API client with automatic token injection
- **Pages:** React components with client-side data fetching using hooks
- **Styling:** Inline CSS for minimal dependencies
- **State Management:** React hooks (useState, useEffect)

### Cloud API Architecture

- **Framework:** FastAPI with SQLAlchemy ORM
- **Authentication:** Header-based token validation via `verify_admin_token` dependency
- **Database:** PostgreSQL with optimized indexes on key columns
- **Pagination:** Offset/limit pattern for consistent data retrieval

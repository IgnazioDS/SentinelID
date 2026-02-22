# SentinelID Deployment Guide (Phase 4)

## Prerequisites

- Docker and Docker Compose
- PostgreSQL 15+
- Python 3.11+
- Node.js 18+

## Local Development Deployment

### 1. Configure Environment

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` with your configuration:

```bash
# Set a secure admin token (use strong random string in production)
ADMIN_API_TOKEN=your-secure-admin-token-here

# Must match ADMIN_API_TOKEN for admin UI to access API
NEXT_PUBLIC_ADMIN_TOKEN=your-secure-admin-token-here

# API URL accessible from browser
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 2. Start Services

```bash
# Build and start all services
docker-compose up --build

# Services will be available at:
# - Admin UI: http://localhost:3000
# - Cloud API: http://localhost:8000
# - PostgreSQL: localhost:5432
```

### 3. Verify Deployment

Once services are running, run smoke tests:

```bash
# Set environment variables
export API_URL=http://localhost:8000
export ADMIN_TOKEN=your-secure-admin-token-here

# Run smoke tests
./scripts/smoke_test_admin.sh
```

Expected output:
```
🔍 Starting Admin Dashboard Smoke Tests
   API URL: http://localhost:8000
   Timeout: 5s

📱 Testing /v1/admin/devices...
   ✓ Status: 200 OK (Found X devices)
📋 Testing /v1/admin/events...
   ✓ Status: 200 OK (Found X events)
📊 Testing /v1/admin/stats...
   ✓ Status: 200 OK
     - Total devices: X
     - Liveness failure rate: X%
🔐 Testing authentication rejection (missing token)...
   ✓ Correctly returned 401 (Unauthorized)
🔐 Testing authentication rejection (invalid token)...
   ✓ Correctly returned 401 (Unauthorized)

✅ All smoke tests passed!
```

### 4. Access Admin Dashboard

Open browser and navigate to `http://localhost:3000`

The dashboard includes three main pages:
- **Events** (`/events`) - View and filter authentication events
- **Statistics** (`/stats`) - View service metrics
- **Devices** (`/devices`) - List registered devices

## Production Deployment

### Network Security

1. **API Authentication Token**
   - Generate a cryptographically secure random token
   - Use environment variable `ADMIN_API_TOKEN`
   - Rotate tokens regularly (recommend every 90 days)

2. **HTTPS/TLS**
   - Deploy behind reverse proxy (nginx, Traefik, etc.)
   - Terminate TLS at proxy
   - Use strong certificates (minimum 2048-bit RSA or P-256)

3. **API Rate Limiting**
   - Implement rate limits on admin endpoints
   - Use WAF or reverse proxy for protection
   - Recommend: 1000 requests/minute per IP

### Database Configuration

1. **Connection Security**
   ```bash
   # Use strong password
   POSTGRES_PASSWORD=your-very-strong-password
   
   # Restrict to internal network only
   ports: # Remove from production, use Docker network instead
   ```

2. **Backups**
   ```bash
   # Daily database backups
   docker exec sentinelid_postgres pg_dump -U admin sentinelid > backup-$(date +%Y%m%d).sql
   ```

3. **Performance Tuning**
   - Adjust PostgreSQL shared_buffers based on available memory
   - Enable query logging for slow query analysis
   - Monitor index usage

### Monitoring

Monitor these key metrics:

**Cloud Service**
- Response time for admin endpoints
- Authentication failures (401 errors)
- Database query performance

**Admin UI**
- Page load times
- API request latency
- Browser console errors

**Database**
- Connection count
- Query execution time
- Disk usage growth

### Environment Variables Reference

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `ADMIN_API_TOKEN` | Yes | `dev-admin-token` | Token for admin API authentication |
| `NEXT_PUBLIC_ADMIN_TOKEN` | Yes | `dev-admin-token` | Token passed by UI to cloud API |
| `NEXT_PUBLIC_API_URL` | Yes | `http://localhost:8000` | Cloud API URL for admin UI |
| `DATABASE_URL` | Yes | Configured in compose | PostgreSQL connection string |
| `POSTGRES_PASSWORD` | Yes | `password` | Database password |
| `POSTGRES_USER` | No | `admin` | Database username |
| `POSTGRES_DB` | No | `sentinelid` | Database name |

### Health Checks

Services include health checks in docker-compose:

**Cloud Service** (HTTP GET `/health`)
- Checks database connectivity
- Verifies application readiness

**Admin UI** (HTTP GET `/`)
- Checks Next.js application availability

**PostgreSQL** (pg_isready)
- Verifies database connectivity

## Troubleshooting

### Cannot Connect to API from Admin UI

**Problem:** Admin UI shows "Failed to load devices" error

**Solution:**
1. Verify `NEXT_PUBLIC_API_URL` is accessible from browser
2. Check `NEXT_PUBLIC_ADMIN_TOKEN` matches `ADMIN_API_TOKEN`
3. Verify cloud service is healthy: `docker-compose ps`
4. Check cloud service logs: `docker-compose logs cloud`

### Authentication Returns 401

**Problem:** API requests return 401 Unauthorized

**Solution:**
1. Verify `X-Admin-Token` header is set in request
2. Ensure token value matches `ADMIN_API_TOKEN` environment variable
3. Check for trailing whitespace in token value
4. Verify no URL encoding of special characters in token

### Database Connection Failures

**Problem:** Cloud service fails to start with connection error

**Solution:**
1. Verify PostgreSQL is running: `docker-compose ps postgres`
2. Check PostgreSQL logs: `docker-compose logs postgres`
3. Verify connection string in `DATABASE_URL`
4. Ensure database exists: `psql postgresql://admin:password@localhost/sentinelid`

## Version History

- **v0.4.0** - Initial Admin Dashboard release with authentication, events/stats/devices pages
- **v0.3.1** - Audit logging and device binding
- **v0.2.0** - Cloud ingest and event processing
- **v0.1.0** - Initial edge application

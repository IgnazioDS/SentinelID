# API

For how to start services and run smoke checks, use `RUNBOOK.md`.

## Edge API (`/api/v1`)

Base URL (local dev): `http://127.0.0.1:8787`

- `GET /health` (unauthenticated process health)
- `GET /api/v1/` (v1 health)
- `GET /api/v1/health` (public v1 health)
- `POST /api/v1/enroll/start`
- `POST /api/v1/enroll/frame`
- `POST /api/v1/enroll/commit`
- `POST /api/v1/enroll/reset`
- `POST /api/v1/enroll/calibrate`
- `POST /api/v1/auth/start`
- `POST /api/v1/auth/frame`
- `POST /api/v1/auth/finish`
- `GET /api/v1/diagnostics`
- `GET /api/v1/settings/telemetry`
- `POST /api/v1/settings/telemetry`
- `POST /api/v1/admin/rotate-key`
- `POST /api/v1/settings/delete_identity`

Auth: all `/api/v1/*` routes require `Authorization: Bearer <EDGE_AUTH_TOKEN>` except health routes.

## Cloud API (`/v1`)

Base URL (local docker): `http://127.0.0.1:8000`

- `GET /health`
- `POST /v1/ingest/events`
- `GET /v1/admin/events`
- `GET /v1/admin/devices`
- `GET /v1/admin/stats`

Auth:
- Admin routes require header `X-Admin-Token: <ADMIN_API_TOKEN>`.
- Ingest routes verify device signatures and reject forbidden telemetry fields.
- Admin stats include latency percentiles (`latency_p50_ms`, `latency_p95_ms`) and `risk_distribution`.

## Admin App Internal API (`/api/admin/session`)

Base URL (local admin): `http://127.0.0.1:3000`

- `POST /api/admin/session/login`
- `POST /api/admin/session/logout`
- `GET /api/admin/session/me`

Auth:
- Login issues an HttpOnly session cookie.
- `/api/cloud/*` proxy routes require a valid session cookie.
- Browser-provided `X-Admin-Token` is ignored by proxy; server injects `ADMIN_API_TOKEN`.

## Contracts

- Shared schemas and OpenAPI artifacts live in `packages/shared-contracts/`.
- Regenerate TypeScript contract types with `make gen-types` (or `scripts/gen_types.sh`).

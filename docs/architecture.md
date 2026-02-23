# Architecture

For setup and run commands, use `RUNBOOK.md`.

## Components

- Desktop (`apps/desktop`): Tauri app and camera UX.
- Edge (`apps/edge`): local FastAPI service for auth policy, liveness, risk scoring, audit, and telemetry signing.
- Cloud (`apps/cloud`): ingest and admin APIs.
- Admin (`apps/admin`): Next.js dashboard for events, devices, and stats.

## Runtime Boundaries

- Desktop to Edge: loopback only (`127.0.0.1`), bearer token protected.
- Edge to Cloud: signed, sanitized telemetry over HTTP(S).
- Admin to Cloud: token-protected admin API.

## Trust Model

- Biometric inference and decisioning happen on-device (edge).
- Cloud receives operational telemetry and verification metadata, not raw biometric artifacts.
- Hash-chained audit events provide tamper-evident local records.

## Data Stores

- Edge: local SQLite (`apps/edge/.sentinelid/audit.db`) for audit/outbox and encrypted templates.
- Cloud: PostgreSQL for registered devices and telemetry events.

## Related Docs

- API: `docs/api.md`
- Privacy: `docs/privacy.md`
- Threat model: `docs/threat-model.md`
- Key management: `docs/KEY_MANAGEMENT.md`

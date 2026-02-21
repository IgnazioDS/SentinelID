# SentinelID

SentinelID is a passkey-style authentication system that replaces passwords with a **liveness-gated face login**, delivered as a **Tauri desktop app** paired with a **hybrid remote admin dashboard**.

- **Desktop (Tauri + React):** camera UI, enrollment/login UX, starts/stops the local Edge service.
- **Edge (local FastAPI):** all computer-vision inference + policy (verify, liveness, spoof/deepfake risk), local secure storage, tamper-evident audit log, sanitized telemetry export.
- **Cloud (remote FastAPI):** telemetry ingest + admin API.
- **Admin (remote Next.js):** dashboards for events, metrics, device health.

> Default posture: **on-device verification** and **no raw face images** stored or uploaded.

---

## Why it exists

Most face-login demos stop at “matching a face.” SentinelID is built around real product constraints:

- **Security:** active liveness, anti-spoof/deepfake risk scoring, rate limiting/lockouts, auditability.
- **Privacy:** store **only encrypted embeddings**; export only **sanitized telemetry**.
- **UX:** fast loopback communication (localhost), deterministic flows, clear reason codes.
- **Operations:** remote dashboard + metrics (latency, outcomes, risk distribution).

---

## System overview

### Authentication pipeline (Edge)

1. **Detect + align** face (landmarks → canonical crop)
2. **Verify** via embeddings (template match)
3. **Active liveness** (randomized blink/head-turn challenges)
4. **Risk scoring** (passive spoof heuristics + optional lightweight classifier)
5. **Policy**: `ALLOW` / `STEP_UP` / `DENY`

### Hybrid architecture

- Desktop ↔ Edge runs on **localhost only** with:
  - **dynamic port** (picked at runtime)
  - **bearer token** required on all routes (except `/v1/health`)
- Edge → Cloud exports **sanitized telemetry only** (no frames).

---

## Security & privacy guarantees (MVP targets)

- **Local-only inference:** verification + liveness + risk scoring runs on-device.
- **No raw video persistence:** frames are processed in-memory; not stored by default.
- **Embeddings encrypted at rest:** templates are stored as encrypted blobs.
- **Tamper-evident audit log:** hash-chained events.
- **Local API hardening:** Edge binds to `127.0.0.1` + requires a per-run bearer token.
- **Telemetry minimization:** only scores/outcomes/timings + audit hashes.
- **Delete identity:** wipe templates/keys/logs from the device.

---

## Repo structure (planned)

> Names may change slightly during implementation; this is the intended blueprint.

```
apps/
  desktop/   # Tauri + React desktop app
  edge/      # Local FastAPI service (CV + auth + storage)
  cloud/     # Remote FastAPI (ingest + admin API)
  admin/     # Remote Next.js admin dashboard
packages/
  shared-contracts/  # OpenAPI + generated TS types
scripts/
  bundle_edge_venv.sh
  eval/
docs/
  architecture.md
  threat-model.md
  privacy.md
  evaluation.md
```

---

## Quickstart (development)

### Prerequisites

- macOS (primary dev target)
- Node.js (LTS)
- Python 3.11+
- Rust toolchain (for Tauri)
- (Optional) Docker (for Cloud/Admin local dev)

### 1) Run Edge locally (dev mode)

From repo root:

```bash
make dev-edge
```

Expected:
- Edge running on `http://127.0.0.1:8787`
- Health check: `GET /v1/health`

### 2) Run Desktop (Tauri)

```bash
make dev-desktop
```

Desktop will connect to Edge on localhost.

### 3) Run Cloud + Admin locally (optional)

```bash
docker compose up --build
```

This starts:
- `apps/cloud` API
- `apps/admin` dashboard
- Postgres

---

## Bundling Edge inside the Desktop app (Option 1)

Production posture: **bundle Python + a self-contained venv**, and have Tauri **spawn the Edge process** on startup.

### Bundle workflow (local build)

```bash
make bundle-edge
```

This builds a venv into `apps/desktop/resources/edge/pyvenv` and packages the Edge app code into `apps/desktop/resources/edge/app`.

At runtime:
- Tauri picks a free **dynamic port**
- generates a per-run **auth token**
- starts Edge via `resources/edge/run_edge.sh`
- polls `/v1/health` until ready

---

## APIs

### Edge API (local)

- `GET /v1/health`
- `POST /v1/enroll/start`
- `POST /v1/enroll/frame`
- `POST /v1/enroll/commit`
- `POST /v1/auth/start`
- `POST /v1/auth/frame`
- `POST /v1/auth/finish`
- `POST /v1/settings/privacy`
- `POST /v1/settings/delete_identity`

All routes (except `/v1/health`) require:

- `Authorization: Bearer <EDGE_AUTH_TOKEN>`

### Cloud API (remote)

- `POST /v1/ingest/events` (Edge → Cloud)
- `POST /v1/admin/login`
- `GET /v1/admin/events`
- `GET /v1/admin/metrics`
- `GET /v1/admin/devices`

OpenAPI specs live under `packages/shared-contracts/`.

---

## Telemetry model (sanitized)

SentinelID does **not** upload face frames. Telemetry includes:

- outcome: `ALLOW` / `STEP_UP` / `DENY`
- similarity score (float)
- risk score (float) + reason codes
- liveness pass/fail + failure reason
- timings (detect/align/embed/liveness/risk/policy)
- audit hash (hash-chain tip)
- device id + signature

---

## Evaluation

The project includes an evaluation harness to measure:

- FAR / FRR (at chosen thresholds)
- liveness pass rate (genuine attempts)
- spoof/deepfake block rate (photo/replay/synthetic)
- latency breakdown

See `docs/evaluation.md` and `scripts/eval/`.

---

## Roadmap (high-level)

- **v0.1**: scaffold + end-to-end loop (desktop ↔ edge), enroll + verify, local storage
- **v0.2**: active liveness (pose + blink), step-up policies
- **v0.3**: spoof/deepfake risk scoring + lockouts + telemetry export
- **v0.4**: cloud ingest + admin dashboard (events/metrics)
- **v0.5**: hardening (encryption, audit hash chain, deletion flow) + polished demo

---

## Non-goals (MVP)

- Multi-user identity management (single-user MVP)
- Perfect deepfake detection (goal is practical risk scoring + measurable defense)
- Cross-platform packaging (Windows/Linux later)

---

## License

TBD.

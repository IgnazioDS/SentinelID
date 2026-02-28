# SentinelID Demo Checklist (v2.3.4)

Target runtime: under 10 minutes for a full manual pass.

Non-interactive verification alternative:

- `make demo-verify` runs smoke/recovery/support-bundle/admin checks without launching the desktop UI.
- Optional scripted desktop close semantics pass:
  - `DEMO_VERIFY_DESKTOP=1 DEMO_VERIFY_DESKTOP_AUTO_CLOSE_SECONDS=20 make demo-verify`

## Preconditions

- From repo root, `.env` exists and `ADMIN_API_TOKEN` is set.
- Docker Desktop (or daemon) is running.
- Camera device is available.

## 10-Step Regression Checklist

1. Start demo stack
- Run `make demo-up`.
- Verify:
  - `http://127.0.0.1:8000/health` returns 200.
  - `http://127.0.0.1:3000` loads.

2. Launch desktop
- Run `make demo-desktop`.
- Verify desktop opens with `Login | Enroll | Settings` tabs and status strip.

3. Enroll (capture N frames, commit)
- Go to `Enroll` tab.
- Start enrollment, capture frames until progress reaches target, commit template.
- Expected: `Enrollment Complete` with template id.

4. Auth success (ALLOW)
- Go to `Login` tab and run verification.
- Expected: final decision `allow` for enrolled user under normal conditions.

5. Trigger STEP_UP
- Trigger a medium-risk path (adjust lighting/pose/motion as needed) until step-up is required.
- Expected: explicit `Additional check required` handoff and successful continuation.

6. Verify denial case
- Trigger a deny condition (`liveness fail` or `similarity below threshold`).
- Expected: final decision `deny` with clear reason message.

7. Cloud-down recovery
- In a second terminal, run `docker compose stop cloud admin`.
- Perform local auth from desktop.
- Expected: auth still completes locally and edge outbox pending/DLQ counters increase.

8. Cloud restore
- Run `docker compose up -d cloud admin`.
- Wait until cloud health is green.
- Expected: outbox drains and events become visible in admin (`/events`).

9. Support bundle sanitization
- From admin UI Support page, generate/download support bundle.
- Validate tarball contains diagnostics/stats/events summaries only and no raw frames, embeddings, tokens, or signatures.

10. Desktop exit process hygiene
- Close desktop app.
- Optional scripted close path: `DEMO_AUTO_CLOSE_SECONDS=30 make demo-desktop`
- CI-friendly scripted close path (no Docker): `make demo-desktop-verify`
- Expected close statuses: `0` (app close), `130` (Ctrl+C), or `143` (terminate) unless strict mode is set.
- Verify no orphan edge process remains:
  - `make check-no-orphans`
  - Canonical script path: `scripts/check_no_orphan_edge.sh`

## Exit

- Shut down demo stack: `make demo-down`
- Optional volume cleanup: `make demo-down V=1`

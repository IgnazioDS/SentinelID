# Pilot Readiness Freeze (v2.6.0 target)

This checklist is used to mark the pilot-ready tag and archive evidence.

## Required Commands

```bash
make release-check
make release-evidence
make runbook-lock
make demo-verify
make pilot-evidence
```

## Evidence Artifacts

- `output/ci/reliability_slo.json`
- `output/ci/invariant_report.json`
- `output/ci/desktop_warning_budget.json`
- `scripts/perf/out/bench_edge_*.json`
- `scripts/support/out/support_bundle_*.tar.gz`
- `output/release/evidence_pack_<timestamp>.tar.gz`
- `output/release/pilot_evidence_<timestamp>.tar.gz`
- `output/release/runbook_lock_<label>.tar.gz`
- CI parity run URLs (PR + main)
- Successful `release-tag` `workflow_dispatch` run URL (post-release validation)

When generating pilot evidence, embed CI links directly in `manifest.json`:

```bash
CI_PARITY_PR_URL="https://github.com/<org>/<repo>/actions/runs/<id>" \
CI_PARITY_MAIN_URL="https://github.com/<org>/<repo>/actions/runs/<id>" \
RELEASE_TAG_DISPATCH_URL="https://github.com/<org>/<repo>/actions/runs/<id>" \
RUNBOOK_LOCK_LABEL="vX.Y.Z" \
make pilot-evidence
```

## Manual Pilot Dry-Run

- Fresh machine setup from `RUNBOOK.md`
- Docker-first startup using `make demo-up`
- Admin UI reachable at `http://127.0.0.1:3000`
- Cloud health reachable at `http://127.0.0.1:8000/health`
- Recovery outage simulation from `make demo-verify`

## Tagging

Only cut `v2.6.0` after evidence artifacts and manual pilot dry-run are complete.

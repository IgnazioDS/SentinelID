# Pilot Readiness Freeze (v2.3.1 target)

This checklist is used to mark the pilot-ready tag and archive evidence.

## Required Commands

```bash
make release-check
make release-evidence
make demo-verify
make pilot-evidence
```

## Evidence Artifacts

- `output/ci/reliability_slo.json`
- `scripts/perf/out/bench_edge_*.json`
- `scripts/support/out/support_bundle_*.tar.gz`
- `output/release/evidence_pack_<timestamp>.tar.gz`
- `output/release/pilot_evidence_<timestamp>.tar.gz`
- CI parity run URLs (PR + main)

## Manual Pilot Dry-Run

- Fresh machine setup from `RUNBOOK.md`
- Docker-first startup using `make demo-up`
- Admin UI reachable at `http://127.0.0.1:3000`
- Cloud health reachable at `http://127.0.0.1:8000/health`
- Recovery outage simulation from `make demo-verify`

## Tagging

Only cut `v2.3.1` after evidence artifacts and manual pilot dry-run are complete.

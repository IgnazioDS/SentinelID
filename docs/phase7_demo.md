# SentinelID Phase 7 Demo (v0.7)

## Prerequisites

- Edge service running locally (default: `http://127.0.0.1:8000`).
- Bearer token available for Edge auth (default dev token: `devtoken`).
- Desktop app camera permissions granted for manual checks.
- Python 3 available for the eval harness runner.

Optional environment knobs:

- `RISK_THRESHOLD_R1` and `RISK_THRESHOLD_R2` to tune allow/step-up/deny policy.
- `MAX_STEP_UPS_PER_SESSION` to limit additional challenge rounds.

## Run The Eval Script

The eval harness is intentionally sanitized and emits only scores/outcomes.

```bash
./scripts/eval/run_eval.sh
```

Optional args:

```bash
./scripts/eval/run_eval.sh <base_url> <token> <attempts>
./scripts/eval/run_eval.sh http://127.0.0.1:8000 devtoken 10
```

Output files are written to:

- `scripts/eval/out/eval_<UTC timestamp>.json`

The JSON output contains only:

- `ts`
- `outcome`
- `risk_score`
- `risk_reasons`
- `liveness_pass`
- `reason_codes`
- `latency_ms`

No raw frames and no embeddings are stored.

## Manual Demo Protocol

Run the Desktop app and perform the following three attempts end-to-end.
Use Demo Mode only for local visual inspection of `risk_score` and `risk_reasons`.

1. Genuine attempt
- Present a live face.
- Complete the prompted liveness challenges naturally.
- If `STEP_UP` appears, complete additional challenges and finish.

2. Printed photo attempt
- Present a printed face photo to the camera.
- Attempt to pass prompts without a live subject.
- Observe whether risk reasons indicate spoof suspicion and whether outcome is `STEP_UP` or `DENY`.

3. Screen replay attempt
- Replay a face video/photo on another screen and present it to the camera.
- Complete the flow until final decision.
- Observe risk reasons and final outcome.

## Expected Outputs And Interpretation

Policy behavior in v0.7:

- `risk < R1`: `ALLOW` if liveness passes.
- `R1 <= risk < R2`: `STEP_UP` (additional randomized challenge round).
- `risk >= R2`: `DENY`.

Interpretation guide:

- `risk_reasons` with spoof indicators (for example `SPOOF_SUSPECT_SCREEN`) should correlate with higher `risk_score`.
- `reason_codes` should include policy/liveness decision context (for example `RISK_STEP_UP`, `RISK_HIGH`, `LIVENESS_PASSED`).
- `latency_ms` can be trended across runs to spot regressions.

For reproducibility, keep camera position, lighting, and distance consistent across scenarios.

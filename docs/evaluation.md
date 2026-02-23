# Evaluation

For full setup and test commands, use `RUNBOOK.md`.

## Scope

SentinelID evaluation focuses on:

- Decision outcomes (`allow`, `step_up`, `deny`)
- Liveness pass/fail behavior
- Risk score and risk reason distribution
- End-to-end latency per auth attempt

## Harness

- Script: `scripts/eval/run_eval.sh`
- Output: `scripts/eval/out/eval_<timestamp>.json`
- Output is sanitized and excludes frames/embeddings.

## Typical Local Run

1. Start edge locally.
2. Run eval script against edge URL and token.
3. Review generated JSON outputs for policy and latency regressions.

Example command is documented in `RUNBOOK.md`.

## Interpretation Notes

- `risk_score < RISK_THRESHOLD_R1`: expected allow path if liveness passes.
- `RISK_THRESHOLD_R1 <= risk_score < RISK_THRESHOLD_R2`: expected step-up path.
- `risk_score >= RISK_THRESHOLD_R2`: expected deny path.

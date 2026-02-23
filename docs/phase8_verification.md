# Phase 8 Verification (v0.8)

## Overview

Phase 8 adds a real verification pipeline on top of liveness and risk policy:

- enrollment session captures `N` good frames
- stable template is aggregated and stored as encrypted blob
- auth finish computes similarity against enrolled template
- policy combines template presence, liveness, similarity, and risk/step-up
- local calibration computes FAR/FRR operating points and recommends threshold

No raw frames are persisted in SQLite or eval reports.

## Enrollment Flow

### API

1. Start

```bash
curl -X POST http://127.0.0.1:8000/api/v1/enroll/start \
  -H 'Authorization: Bearer devtoken' \
  -H 'Content-Type: application/json' \
  -d '{}'
```

2. Send frame(s)

```bash
curl -X POST http://127.0.0.1:8000/api/v1/enroll/frame \
  -H 'Authorization: Bearer devtoken' \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"<SESSION_ID>","frame":"data:image/jpeg;base64,..."}'
```

3. Commit template

```bash
curl -X POST http://127.0.0.1:8000/api/v1/enroll/commit \
  -H 'Authorization: Bearer devtoken' \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"<SESSION_ID>","label":"default"}'
```

4. Reset session (optional)

```bash
curl -X POST http://127.0.0.1:8000/api/v1/enroll/reset \
  -H 'Authorization: Bearer devtoken' \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"<SESSION_ID>"}'
```

### Desktop

Use the **Enrollment** mode in the camera UI:

- Start Enrollment
- Capture frames until progress reaches target
- Commit Enrollment

The UI surfaces quality feedback (`NO_FACE`, `TOO_BLURRY`, `POSE_TOO_LARGE`, etc.).

## Verification Decision Precedence

At `/api/v1/auth/finish`:

1. no enrolled template -> `DENY` + `NOT_ENROLLED`
2. liveness fail -> `DENY`
3. similarity below threshold -> `DENY` + `SIMILARITY_BELOW_THRESHOLD`
4. else apply risk policy:
- `risk >= R2` -> `DENY`
- `R1 <= risk < R2` -> `STEP_UP`
- `risk < R1` -> `ALLOW`

Response fields include:

- `similarity_score`
- `risk_score`
- `reason_codes`
- `risk_reasons`
- `quality_reason_codes`

## Threshold Calibration

Create two local folders:

- `genuine/`: same enrolled subject
- `impostor/`: different subjects

Run:

```bash
./scripts/eval/run_verify_eval.sh ./data/genuine ./data/impostor 0.01
```

Output:

- `scripts/eval/out/verify_eval_<timestamp>.json`

The report includes:

- genuine/impostor score distributions
- operating curve (`threshold`, `far`, `frr`)
- `recommended_threshold` for target FAR
- approximate EER point

## FAR / FRR Interpretation

- **FAR** (False Accept Rate): impostor samples incorrectly accepted.
- **FRR** (False Reject Rate): genuine samples incorrectly rejected.

Typical tuning process:

1. Set a target FAR (for example `0.01`).
2. Use `recommended_threshold` from calibration output.
3. Validate resulting FRR on your expected user conditions.
4. Set `SIMILARITY_THRESHOLD` in environment/config and re-run eval.

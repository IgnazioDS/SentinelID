# Phase 2 Quick Start Guide

## TL;DR - Run Everything in 5 Minutes

### 1️⃣ Start Edge Service (Terminal 1)
```bash
cd /Users/ignaziodesantis/Desktop/Development/SentinelID
source ./apps/edge/.venv/bin/activate
EDGE_AUTH_TOKEN=devtoken EDGE_ENV=dev python -m uvicorn \
  sentinelid_edge.main:app --host 127.0.0.1 --port 8787
```

### 2️⃣ Start Desktop App (Terminal 2)
```bash
cd /Users/ignaziodesantis/Desktop/Development/SentinelID/apps/desktop
npm run tauri dev
```

### 3️⃣ Test Liveness Flow
```bash
# In Desktop app UI:
1. Click "Start Authentication"
2. Allow camera access
3. Perform challenge (blink or turn head)
4. See "✓ Authentication Successful" or "✗ Failed"
```

---

## What Was Built

### Edge Service (Backend)
**Location**: `apps/edge/sentinelid_edge/`

```
Domain Models:
├── domain/reasons.py         → Reason codes (17+)
├── domain/models.py          → Challenge, AuthSession
└── domain/policy.py          → PolicyEngine + AuthDecision

Liveness Detection:
├── services/liveness/challenges.py  → SessionStore, ChallengeGenerator
├── services/liveness/blink.py       → Eye Aspect Ratio detection
├── services/liveness/pose.py        → Yaw/head turn detection
├── services/liveness/evaluator.py   → Main liveness evaluator
└── services/vision/detector.py      → Face detector (mock landmarks)

API Endpoints:
└── api/v1/auth.py           → /start, /frame, /finish (fully wired)

Tests:
├── tests/test_liveness.py   → 20+ tests (blink, pose, session, generator)
└── tests/test_policy.py     → 19+ tests (policy, decisions, transitions)
```

### Desktop App (Frontend)
**Location**: `apps/desktop/src/features/camera/`

```
UI Components:
├── CameraView.tsx           → Full state machine (idle → challenge → result)
└── CameraView.css           → Responsive styling

Features:
- 6 UI states (idle, starting, in_challenge, finishing, success, error)
- 8fps frame streaming to edge
- Real-time progress display
- Dynamic challenge instructions
- Success/failure with reason codes
```

---

## API Endpoints

### POST /api/v1/auth/start
Start a liveness session with randomized challenges.

**Request:**
```json
{}
```

**Response:**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "challenges": ["blink", "turn_right"]
}
```

---

### POST /api/v1/auth/frame
Send a frame for the current challenge.

**Request:**
```json
{
  "session_id": "550e8400-...",
  "frame": "data:image/jpeg;base64,/9j/4AAQSkZJ..."
}
```

**Response:**
```json
{
  "session_id": "550e8400-...",
  "current_challenge": "turn_right",
  "progress": "1/2 challenges",
  "detail": "Blink detected. Moving to next challenge..."
}
```

---

### POST /api/v1/auth/finish
Get the final authentication decision.

**Request:**
```json
{
  "session_id": "550e8400-..."
}
```

**Response (Allow):**
```json
{
  "decision": "allow",
  "reason_codes": ["LIVENESS_PASSED"],
  "liveness_passed": true,
  "similarity_score": null
}
```

**Response (Deny):**
```json
{
  "decision": "deny",
  "reason_codes": ["LIVENESS_FAILED", "BLINK_NOT_DETECTED"],
  "liveness_passed": false,
  "similarity_score": null
}
```

---

## Key Features

### ✅ Randomized Challenges
- 2-3 challenges per session
- Random order each time
- Types: BLINK, TURN_LEFT, TURN_RIGHT

### ✅ Liveness Detection
- **Blink**: Eye Aspect Ratio (EAR) with hysteresis
- **Head Turn**: Yaw estimation with state machine
- Mock landmarks for dev (ready for real face detector)

### ✅ Policy Engine
- Enforces liveness requirement
- Returns detailed reason codes
- Session timeout handling (120s)
- Challenge timeout handling (10s per challenge)

### ✅ UI State Machine
- 6 states: idle, starting, in_challenge, finishing, success, error
- 8fps frame streaming
- Real-time progress updates
- Dynamic challenge instructions
- Mobile-friendly responsive design

### ✅ Security
- Bearer token authentication
- Localhost-only binding (127.0.0.1)
- No frame persistence to disk
- CORS dev-only (no wildcard)
- Session TTL with cleanup

---

## Test Coverage

```bash
# Run all tests
cd ./apps/edge
pytest tests/test_liveness.py tests/test_policy.py -v

# Run specific test suite
pytest tests/test_liveness.py::TestBlinkDetector -v
pytest tests/test_policy.py::TestPolicyEngine -v

# Run with coverage
pytest tests/test_liveness.py tests/test_policy.py --cov=sentinelid_edge.services.liveness
```

**Test Count**: 39+ tests across:
- Blink detection (6 tests)
- Head pose detection (6 tests)
- Session management (4 tests)
- Challenge generation (3 tests)
- Policy engine (10 tests)
- State transitions (4 tests)
- Response formats (3 tests)

---

## Environment Variables

### Edge Service
```bash
EDGE_ENV=dev              # dev or prod (controls CORS)
EDGE_AUTH_TOKEN=devtoken  # Bearer token
```

### Desktop App
- No explicit env vars needed
- Auto-detects Edge base_url + token via Tauri command

---

## File Checklist

### New Files (8)
- ✅ `domain/reasons.py`
- ✅ `domain/models.py`
- ✅ `domain/policy.py`
- ✅ `services/liveness/challenges.py`
- ✅ `services/liveness/blink.py`
- ✅ `services/liveness/pose.py`
- ✅ `services/liveness/evaluator.py`
- ✅ `services/vision/detector.py`
- ✅ `tests/test_liveness.py`
- ✅ `tests/test_policy.py`
- ✅ `src/features/camera/CameraView.css`

### Modified Files (2)
- ✅ `api/v1/auth.py` (complete rewrite)
- ✅ `src/features/camera/CameraView.tsx` (full state machine)

---

## Commits (6 Total)

```
0caf8e5 feat(edge): define domain models and reason codes
8a98715 feat(edge): liveness session store + randomized challenges
8287e38 feat(edge): implement liveness evaluator + vision detector stub
d583dbe feat(edge): wire auth endpoints to liveness evaluator + reason codes
6240178 test(edge): add comprehensive liveness + policy tests
279fbc2 feat(desktop): liveness challenge UI flow + frame streaming
```

---

## Branch Status

```bash
# Current branch
git branch -vv

# Expected output
* feat/liveness-v0.2  279fbc2 [origin/feat/liveness-v0.2] feat(desktop): liveness challenge UI flow + frame streaming
  main                8785466 [origin/main] Merge branch 'feat/secure-loopback-v0.1'

# Pre-release tag
git tag -l v0.*
# Expected: v0.1.0, v0.1.0-alpha.1, v0.2.0-alpha.1
```

---

## Next Steps

1. **Test Everything** (use "TL;DR" above)
2. **Review Code** (6 commits, ~2,500 LOC)
3. **Run Unit Tests** (39+ tests)
4. **Merge to Main** (see PHASE2_MERGE_INSTRUCTIONS.md)
5. **Create Release Tag** (v0.2.0)
6. **Deploy** (when ready)

---

## Troubleshooting

### Port Already in Use
```bash
# Find process using port 8787
lsof -i :8787

# Use different port
python -m uvicorn sentinelid_edge.main:app --host 127.0.0.1 --port 9000
```

### Camera Permission Denied
```bash
# Check camera permissions (macOS)
System Preferences → Security & Privacy → Camera → Allow browser
```

### Tests Failing
```bash
# Reinstall dependencies
cd ./apps/edge
poetry install --no-cache
pytest tests/test_liveness.py -v
```

### Desktop Build Issues
```bash
# Clean and rebuild
rm -rf ./apps/desktop/src-tauri/target
cargo build --manifest-path ./apps/desktop/src-tauri/Cargo.toml --release
npm run tauri dev
```

---

## Architecture Diagram

```
User → Desktop UI (React)
        ↓ (start_auth)
        Edge /auth/start (SessionStore creates session)
        ↓ (session_id + challenges)
User performs action → Desktop streams frames (8fps)
        ↓ (/auth/frame per frame)
        Edge FaceDetector + LivenessEvaluator
        ├─ BlinkDetector (EAR calculation)
        ├─ HeadPoseDetector (yaw estimation)
        └─ Challenge completion check
        ↓ (current_challenge + progress)
After challenges complete → Desktop calls /auth/finish
        ↓
        Edge PolicyEngine evaluates session
        ↓ (decision + reason_codes)
        Desktop displays result (✓ or ✗)
```

---

**Phase 2 Ready to Test!** 🚀

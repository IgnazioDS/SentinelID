# Phase 2 Merge Instructions

## Current Status
- **Branch**: `feat/liveness-v0.2`
- **Tag**: `v0.2.0-alpha.1` (already pushed)
- **Commits**: 6 well-scoped commits
- **Status**: ✅ Ready for testing and merge

---

## Pre-Merge Testing Checklist

### 1. Run Unit Tests
```bash
cd ./apps/edge
poetry install  # if needed
pytest tests/test_liveness.py -v
pytest tests/test_policy.py -v
pytest tests/ -v  # all tests
```

**Expected**: All tests pass (39+ tests)

---

### 2. Run Edge Standalone

**Terminal 1:**
```bash
cd /Users/ignaziodesantis/Desktop/Development/SentinelID
source ./apps/edge/.venv/bin/activate
EDGE_AUTH_TOKEN=devtoken EDGE_ENV=dev python -m uvicorn \
  sentinelid_edge.main:app \
  --host 127.0.0.1 \
  --port 8787
```

**Terminal 2 - Test Auth Flow:**
```bash
# 1. Start session
curl -X POST http://127.0.0.1:8787/api/v1/auth/start \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer devtoken" \
  -d '{}'

# Copy the session_id from response

# 2. Send a frame (use base64 image or mock)
curl -X POST http://127.0.0.1:8787/api/v1/auth/frame \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer devtoken" \
  -d '{
    "session_id": "YOUR_SESSION_ID_HERE",
    "frame": "data:image/jpeg;base64,/9j/4AAQSkZJRgABA..."
  }'

# 3. Finish auth
curl -X POST http://127.0.0.1:8787/api/v1/auth/finish \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer devtoken" \
  -d '{"session_id": "YOUR_SESSION_ID_HERE"}'
```

**Expected responses**:
- `/auth/start`: 200 with `{session_id, challenges}`
- `/auth/frame`: 200 with `{session_id, current_challenge, progress, detail}`
- `/auth/finish`: 200 with `{decision, reason_codes, liveness_passed}`

---

### 3. Run Desktop with Auto-spawned Edge

**Terminal 1:**
```bash
cd /Users/ignaziodesantis/Desktop/Development/SentinelID/apps/desktop
npm run tauri dev
```

**Expected**:
- App loads with "Loading..." message
- After ~2-3 seconds: Camera UI appears
- Button: "Start Authentication"
- Click button → challenges appear
- Frames stream at 8fps
- After challenges complete → "✓ Authentication Successful" or "✗ Failed"

---

## Merge Process

### Option 1: Merge via GitHub PR (Recommended)

```bash
# The branch is already pushed
# Visit: https://github.com/IgnazioDS/SentinelID/pull/new/feat/liveness-v0.2

# 1. Click "Create Pull Request"
# 2. Add title: "feat: add liveness detection + policy engine (Phase 2)"
# 3. Add description (copy from summary below)
# 4. Wait for any CI checks
# 5. Click "Merge pull request" → "Confirm merge"
# 6. Delete branch after merge
```

---

### Option 2: Merge Locally

```bash
# From project root
cd /Users/ignaziodesantis/Desktop/Development/SentinelID

# 1. Switch to main
git switch main

# 2. Merge feature branch
git merge --no-ff feat/liveness-v0.2

# 3. Push to remote
git push origin main

# 4. Create final release tag on main
git tag v0.2.0 main
git push origin v0.2.0

# 5. Verify merge
git log --oneline -5

# 6. Optional: Delete feature branch locally and remotely
git branch -d feat/liveness-v0.2
git push origin --delete feat/liveness-v0.2
```

---

## PR Description Template

```markdown
## Phase 2: Liveness Detection + Policy Engine

### Summary
Implements active liveness verification with randomized challenge-response and policy-gated authentication.

### Changes
- ✅ Liveness evaluators (blink detection via EAR, head turn detection via yaw)
- ✅ Session management with TTL cleanup
- ✅ Randomized challenge generator (2-3 challenges from: blink, turn_left, turn_right)
- ✅ Policy engine with reason codes
- ✅ Auth endpoints: /start, /frame, /finish fully wired
- ✅ Desktop UI state machine with frame streaming (8fps)
- ✅ 39+ unit tests with full coverage
- ✅ Mock face detector (ready for insightface integration)

### Files Changed
- 13 new/modified files
- 6 commits
- ~2,500 lines of code
- ~600 lines of tests

### Testing
- Unit tests: `pytest tests/test_liveness.py tests/test_policy.py`
- Edge standalone: `python -m uvicorn sentinelid_edge.main:app --host 127.0.0.1 --port 8787`
- Desktop app: `npm run tauri dev` (auto-spawns Edge)

### Security
- ✅ Bearer token enforcement maintained
- ✅ Localhost-only binding (127.0.0.1)
- ✅ No frames written to disk
- ✅ Session TTL + cleanup
- ✅ CORS dev-only

### Known Limitations
- Face detector uses mock landmarks (production: insightface)
- Similarity scoring not enforced (future)
- No deepfake detection (future)
```

---

## After Merge Checklist

- [ ] Verify `main` branch includes all Phase 2 commits
- [ ] Tag `v0.2.0` exists on main
- [ ] Feature branch deleted from GitHub (optional)
- [ ] Tests still pass on main: `pytest tests/test_liveness.py tests/test_policy.py`
- [ ] Desktop app still builds: `cargo build --manifest-path ./apps/desktop/src-tauri/Cargo.toml`
- [ ] Documentation updated if needed

---

## Next Phase (Phase 3 - Optional)

Future enhancements:
- [ ] Real face detection (insightface integration)
- [ ] Template matching (similarity scoring)
- [ ] Deepfake detection
- [ ] Advanced challenge types (smile, eye gaze)
- [ ] Telemetry/audit logging
- [ ] Enrollment flow integration

---

## Support & Troubleshooting

### Test Failures
```bash
# Re-run with verbose output
pytest tests/test_liveness.py -vv -s

# Run specific test
pytest tests/test_liveness.py::TestBlinkDetector::test_blink_detection_sequence -v
```

### Desktop App Issues
```bash
# Clear cache
rm -rf ./apps/desktop/src-tauri/target

# Rebuild
cargo build --manifest-path ./apps/desktop/src-tauri/Cargo.toml
npm run tauri dev
```

### Edge Service Issues
```bash
# Check if port is in use
lsof -i :8787

# Use different port
python -m uvicorn sentinelid_edge.main:app --host 127.0.0.1 --port 9000
```

---

## Commit Messages

All commits follow conventional commits format:

```
feat(edge): define domain models and reason codes
feat(edge): liveness session store + randomized challenges
feat(edge): implement liveness evaluator + vision detector stub
feat(edge): wire auth endpoints to liveness evaluator + reason codes
test(edge): add comprehensive liveness + policy tests
feat(desktop): liveness challenge UI flow + frame streaming
```

---

**Ready to merge!** 🚀

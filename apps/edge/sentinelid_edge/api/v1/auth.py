"""
Authentication endpoints with liveness verification and risk-based step-up.

Flow (v0.7):
    POST /auth/start   -- create session, get primary challenges
    POST /auth/frame   -- stream frames; accumulates risk score + landmark history
    POST /auth/finish  -- evaluate; may return step_up=True with extra challenges
        (client runs more /auth/frame calls then calls /auth/finish again for
        the final allow/deny)
"""
from __future__ import annotations

import logging
import time
from typing import List, Optional

import numpy as np

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ...core.config import settings
from ...domain.models import AuthSession
from ...domain.policy import PolicyEngine
from ...domain.reasons import ReasonCode
from ...services.antifraud.risk import get_risk_scorer
from ...services.liveness.challenges import ChallengeGenerator, SessionStore
from ...services.liveness.evaluator import LivenessEvaluator
from ...services.observability.perf import get_perf_registry
from ...services.processing.frame_control import get_frame_controller
from ...services.storage.repo_audit import AuditEvent, AuditRepository
from ...services.storage.repo_templates import TemplateRepository
from ...services.telemetry.runtime import get_telemetry_runtime
from ...services.telemetry.event import TelemetryMapper
from ...services.vision.detector import FaceDetector, ModelUnavailableError
from ...services.vision.embedder import FaceEmbedder, cosine_similarity
from ...services.vision.quality import FaceQualityGate

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Global singleton instances
# ---------------------------------------------------------------------------
_session_store = SessionStore(session_timeout_seconds=settings.MAX_SESSION_LIFETIME_SECONDS)
_challenge_generator = ChallengeGenerator(challenge_timeout_seconds=10)
_liveness_evaluator = LivenessEvaluator()
_face_detector = FaceDetector()
_face_embedder = FaceEmbedder(_face_detector)
_face_quality_gate = FaceQualityGate()
_perf = get_perf_registry()
_frame_controller = get_frame_controller()
_policy_engine = PolicyEngine(
    similarity_threshold=settings.SIMILARITY_THRESHOLD,
    risk_threshold_r1=settings.RISK_THRESHOLD_R1,
    risk_threshold_r2=settings.RISK_THRESHOLD_R2,
    max_step_ups=settings.MAX_STEP_UPS_PER_SESSION,
)
_template_repo = TemplateRepository(
    db_path=settings.DB_PATH,
    keychain_dir=settings.KEYCHAIN_DIR,
)
_audit_repo = AuditRepository()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class StartAuthRequest(BaseModel):
    pass


class StartAuthResponse(BaseModel):
    session_id: str
    challenges: List[str]


class AuthFrameRequest(BaseModel):
    session_id: str
    frame: str  # base64-encoded image


class AuthFrameResponse(BaseModel):
    session_id: str
    current_challenge: str
    progress: str
    detail: str
    in_step_up: bool = False
    quality_reason_codes: List[str] = Field(default_factory=list)


class FinishAuthRequest(BaseModel):
    session_id: str


class FinishAuthResponse(BaseModel):
    decision: str  # "allow", "deny", or "step_up"
    reason_codes: List[str]
    liveness_passed: bool
    similarity_score: Optional[float] = None
    risk_score: Optional[float] = None
    risk_reasons: List[str] = Field(default_factory=list)
    quality_reason_codes: List[str] = Field(default_factory=list)
    # Step-up fields (populated when decision == "step_up")
    step_up: bool = False
    step_up_challenges: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _progress_str(session: AuthSession) -> str:
    """Return a human-readable challenge progress string."""
    if session.in_step_up:
        done = sum(1 for c in session.step_up_challenges if c.completed)
        total = len(session.step_up_challenges)
        return f"step-up {done}/{total} challenges"
    done = sum(1 for c in session.challenges if c.completed)
    total = len(session.challenges)
    return f"{done}/{total} challenges"


def _current_challenge_name(session: AuthSession) -> str:
    """Return the name of the active challenge."""
    if session.in_step_up:
        ch = session.get_current_step_up_challenge()
    else:
        ch = session.get_current_challenge()
    return ch.challenge_type.value if ch else "finished"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/start", response_model=StartAuthResponse)
async def start_authentication(request: StartAuthRequest) -> StartAuthResponse:
    """
    Start an authentication session with randomised liveness challenges.
    """
    try:
        challenges_list = _challenge_generator.generate_challenges()
        session = _session_store.create_session(challenges_list)
        _liveness_evaluator.reset_detectors()
        challenge_names = [c.challenge_type.value for c in challenges_list]
        return StartAuthResponse(
            session_id=session.session_id,
            challenges=challenge_names,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start authentication: {exc}",
        )


@router.post("/frame", response_model=AuthFrameResponse)
async def auth_frame(request: AuthFrameRequest) -> AuthFrameResponse:
    """
    Process a single video frame.

    - Accumulates landmark history for temporal risk heuristic.
    - Runs risk scorer on every frame; keeps the session max risk score.
    - Routes challenge evaluation to the primary or step-up challenge set
      depending on session.in_step_up.
    """
    processed_frame = False
    session_id = request.session_id
    try:
        session = _session_store.get_session(request.session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found or expired",
            )

        if session.finished:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Session already finished",
            )

        # Enforce max frames per session
        session.frame_count += 1
        if session.frame_count > settings.MAX_FRAMES_PER_SESSION:
            session.finished = True
            _session_store.save_session(session)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Frame limit exceeded for this session",
            )

        # Adaptive processing gate: cap FPS and drop when processing is backed up.
        acquired, drop_reason = _frame_controller.try_acquire(session.session_id)
        if not acquired:
            _session_store.save_session(session)
            drop_detail = (
                "Frame dropped due processing backlog"
                if drop_reason == "queue_backed_up"
                else f"Frame dropped due rate cap ({settings.FRAME_PROCESSING_MAX_FPS:.1f} fps)"
            )
            return AuthFrameResponse(
                session_id=session.session_id,
                current_challenge=_current_challenge_name(session),
                progress=_progress_str(session),
                detail=drop_detail,
                in_step_up=session.in_step_up,
                quality_reason_codes=[],
            )

        with _perf.stage("frame.decode"):
            image_bgr = _face_detector.decode_frame_to_bgr(request.frame)

        with _perf.stage("frame.detect_landmarks"):
            if image_bgr is None:
                faces = []
                meta = {"num_faces": 0, "reason_codes": [ReasonCode.NO_FACE], "detector_backend": "decode_error"}
            else:
                faces, meta = _face_detector.detect_faces_from_bgr(image_bgr)

        if meta.get("model_unavailable") and not meta.get("fallback_used"):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "detail": "Face model unavailable",
                    "reason_codes": [ReasonCode.MODEL_UNAVAILABLE.value],
                },
            )

        landmarks = faces[0].landmarks if len(faces) == 1 else None

        if len(faces) == 0:
            session.latest_quality_reasons = [ReasonCode.NO_FACE]
            _session_store.save_session(session)
            processed_frame = True
            return AuthFrameResponse(
                session_id=session.session_id,
                current_challenge=_current_challenge_name(session),
                progress=_progress_str(session),
                detail="No face detected in frame",
                in_step_up=session.in_step_up,
                quality_reason_codes=[ReasonCode.NO_FACE.value],
            )

        if len(faces) > 1:
            session.latest_quality_reasons = [ReasonCode.MULTIPLE_FACES]
            _session_store.save_session(session)
            processed_frame = True
            return AuthFrameResponse(
                session_id=session.session_id,
                current_challenge=_current_challenge_name(session),
                progress=_progress_str(session),
                detail="Multiple faces detected; expected exactly one face",
                in_step_up=session.in_step_up,
                quality_reason_codes=[ReasonCode.MULTIPLE_FACES.value],
            )

        # Quality gates for verification embedding capture.
        quality_report = _face_quality_gate.evaluate(image_bgr, faces) if image_bgr is not None else None
        if quality_report is not None and quality_report.passed:
            try:
                with _perf.stage("frame.embed"):
                    embedding = _face_embedder.extract_embedding(
                        request.frame,
                        face=faces[0],
                        image_bgr=image_bgr,
                    )
            except ModelUnavailableError:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail={
                        "detail": "Face model unavailable",
                        "reason_codes": [ReasonCode.MODEL_UNAVAILABLE.value],
                    },
                )
            if embedding is not None:
                session.latest_embedding = np.asarray(embedding, dtype=np.float32)
                if _face_embedder.last_fallback_used:
                    session.latest_quality_reasons = [ReasonCode.FALLBACK_EMBEDDING_USED]
                else:
                    session.latest_quality_reasons = []
            else:
                session.latest_quality_reasons = [ReasonCode.LOW_QUALITY]
        elif quality_report is not None:
            session.latest_quality_reasons = list(quality_report.reason_codes)
        else:
            session.latest_quality_reasons = [ReasonCode.LOW_QUALITY]

        # Accumulate landmark history for temporal heuristic (cap at 40 frames)
        if landmarks is not None:
            session.landmark_history.append(landmarks)
            if len(session.landmark_history) > 40:
                session.landmark_history = session.landmark_history[-40:]

        # Risk scoring: run on every frame; keep session max
        scorer = get_risk_scorer()
        with _perf.stage("frame.risk"):
            risk_result = scorer.score_frame(
                frame_data=request.frame,
                landmarks=landmarks,
                landmark_history=session.landmark_history,
            )
        if risk_result.risk_score > session.risk_score:
            session.risk_score = risk_result.risk_score
            # Merge reason codes (deduped)
            for reason in risk_result.risk_reasons:
                if reason not in session.risk_reasons:
                    session.risk_reasons.append(reason)

        # Challenge processing: primary or step-up
        with _perf.stage("frame.liveness"):
            if session.in_step_up:
                challenge_completed, detail_msg = _liveness_evaluator.process_frame(
                    session,
                    request.frame,
                    landmarks,
                    use_step_up=True,
                )
                if challenge_completed:
                    if session.has_next_step_up_challenge():
                        session.move_to_next_step_up_challenge()
                        _liveness_evaluator.reset_detectors()
                        detail_msg += " Moving to next step-up challenge..."
                    else:
                        _liveness_evaluator.evaluate_session_result(session)
            else:
                challenge_completed, detail_msg = _liveness_evaluator.process_frame(
                    session, request.frame, landmarks
                )
                if challenge_completed:
                    if session.has_next_challenge():
                        session.move_to_next_challenge()
                        _liveness_evaluator.reset_detectors()
                        detail_msg += " Moving to next challenge..."
                    else:
                        _liveness_evaluator.evaluate_session_result(session)

        with _perf.stage("frame.storage"):
            _session_store.save_session(session)
        processed_frame = True

        return AuthFrameResponse(
            session_id=session.session_id,
            current_challenge=_current_challenge_name(session),
            progress=_progress_str(session),
            detail=detail_msg,
            in_step_up=session.in_step_up,
            quality_reason_codes=[
                code.value if hasattr(code, "value") else str(code)
                for code in session.latest_quality_reasons
            ],
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Frame processing error: {exc}",
        )
    finally:
        _frame_controller.release(session_id, processed=processed_frame)


@router.post("/finish", response_model=FinishAuthResponse)
async def finish_authentication(request: FinishAuthRequest) -> FinishAuthResponse:
    """
    Finish the authentication session and obtain the policy decision.

    First call:
        May return decision="step_up" with additional challenge names when
        risk score is in [R1, R2).  The session remains open; the client
        must complete step-up challenges via /auth/frame and then call
        /auth/finish again.

    Second call (after step-up):
        force_final=True is applied; always returns "allow" or "deny".
    """
    session_start_time = None
    try:
        session = _session_store.get_session(request.session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found or expired",
            )

        session_start_time = session.created_at

        # force_final=True on second finish call (step-up already consumed)
        force_final = session.in_step_up

        latest_template = _template_repo.load_latest_template()
        template_enrolled = latest_template is not None
        similarity_score: Optional[float] = None
        if template_enrolled and latest_template is not None and session.latest_embedding is not None:
            similarity_score = cosine_similarity(
                np.asarray(session.latest_embedding, dtype=np.float32),
                np.asarray(latest_template.embedding, dtype=np.float32),
            )
        session.similarity_score = similarity_score

        with _perf.stage("finish.policy"):
            auth_decision = _policy_engine.evaluate(
                session,
                risk_score=session.risk_score,
                risk_reasons=session.risk_reasons,
                template_enrolled=template_enrolled,
                similarity_score=similarity_score,
                enforce_similarity=True,
                force_final=force_final,
            )

        # --- Handle STEP_UP: issue additional challenges, keep session open ---
        if auth_decision.decision == "step_up":
            step_up_reason_codes = list(auth_decision.reason_codes)
            if (
                ReasonCode.FALLBACK_EMBEDDING_USED in session.latest_quality_reasons
                and ReasonCode.FALLBACK_EMBEDDING_USED not in step_up_reason_codes
            ):
                step_up_reason_codes.append(ReasonCode.FALLBACK_EMBEDDING_USED)
            step_up_challenges = _challenge_generator.generate_challenges()
            session.start_step_up(step_up_challenges)
            # Reset liveness evaluator for fresh step-up challenge evaluation
            _liveness_evaluator.reset_detectors()
            with _perf.stage("finish.storage"):
                _session_store.save_session(session)

            step_up_names = [c.challenge_type.value for c in step_up_challenges]
            return FinishAuthResponse(
                decision="step_up",
                reason_codes=step_up_reason_codes,
                liveness_passed=auth_decision.liveness_passed,
                similarity_score=auth_decision.similarity_score,
                risk_score=auth_decision.risk_score,
                risk_reasons=auth_decision.risk_reasons,
                quality_reason_codes=[
                    code.value if hasattr(code, "value") else str(code)
                    for code in session.latest_quality_reasons
                ],
                step_up=True,
                step_up_challenges=step_up_names,
            )

        # --- Final decision (allow or deny): mark session finished ---
        was_in_step_up = session.in_step_up
        final_reason_codes = list(auth_decision.reason_codes)
        if was_in_step_up:
            marker = (
                ReasonCode.STEP_UP_COMPLETED
                if auth_decision.decision == "allow"
                else ReasonCode.STEP_UP_FAILED
            )
            if marker not in final_reason_codes:
                final_reason_codes.append(marker)
        if (
            auth_decision.decision == "deny"
            and ReasonCode.SIMILARITY_BELOW_THRESHOLD in final_reason_codes
        ):
            for code in session.latest_quality_reasons:
                if code not in final_reason_codes:
                    final_reason_codes.append(code)
        if (
            ReasonCode.FALLBACK_EMBEDDING_USED in session.latest_quality_reasons
            and ReasonCode.FALLBACK_EMBEDDING_USED not in final_reason_codes
        ):
            final_reason_codes.append(ReasonCode.FALLBACK_EMBEDDING_USED)

        session.finished = True
        session.clear_step_up()
        session.decision = auth_decision.decision
        session.reason_codes = final_reason_codes
        session.liveness_passed = auth_decision.liveness_passed
        session.similarity_score = auth_decision.similarity_score

        with _perf.stage("finish.storage"):
            _session_store.save_session(session)

        # Audit event (mandatory, append-only)
        audit_event = AuditEvent(
            event_id="",
            timestamp=int(time.time()),
            event_type="auth_finished",
            outcome=auth_decision.decision,
            reason_codes=final_reason_codes,
            similarity_score=auth_decision.similarity_score,
            risk_score=auth_decision.risk_score,
            liveness_passed=auth_decision.liveness_passed,
            session_id=request.session_id,
        )
        with _perf.stage("finish.storage.audit"):
            audit_hash = _audit_repo.write_event(audit_event)

        # Telemetry (optional, never fails auth)
        telemetry_runtime = get_telemetry_runtime()
        if telemetry_runtime:
            try:
                telemetry_event = TelemetryMapper.from_audit_event(
                    audit_event,
                    device_id=telemetry_runtime.exporter.signer.get_device_id(),
                    session_start_time=session_start_time,
                )
                telemetry_event.audit_event_hash = audit_hash
                with _perf.stage("finish.exporter.queue"):
                    telemetry_runtime.record_event(telemetry_event)
            except Exception:
                logger.error(
                    "Telemetry emission failed (session=%s)", request.session_id
                )

        return FinishAuthResponse(
            decision=auth_decision.decision,
            reason_codes=final_reason_codes,
            liveness_passed=auth_decision.liveness_passed,
            similarity_score=auth_decision.similarity_score,
            risk_score=auth_decision.risk_score,
            risk_reasons=auth_decision.risk_reasons,
            quality_reason_codes=[
                code.value if hasattr(code, "value") else str(code)
                for code in session.latest_quality_reasons
            ],
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error finishing authentication: {exc}",
        )

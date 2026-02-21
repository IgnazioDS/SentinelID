"""
Authentication endpoints with liveness verification.
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, status
from pydantic import BaseModel
from typing import Optional, List
from ...services.liveness.challenges import SessionStore, ChallengeGenerator
from ...services.liveness.evaluator import LivenessEvaluator
from ...services.vision.detector import FaceDetector
from ...domain.policy import PolicyEngine
from ...domain.reasons import ReasonCode, get_reason_messages

router = APIRouter()

# Global singleton instances (in production, would use dependency injection)
_session_store = SessionStore(session_timeout_seconds=120)
_challenge_generator = ChallengeGenerator(challenge_timeout_seconds=10)
_liveness_evaluator = LivenessEvaluator()
_face_detector = FaceDetector()
_policy_engine = PolicyEngine()


# Request/Response models
class StartAuthRequest(BaseModel):
    """Request model for starting authentication."""
    pass  # No parameters needed for now


class StartAuthResponse(BaseModel):
    """Response model for starting authentication."""
    session_id: str
    challenges: List[str]


class AuthFrameRequest(BaseModel):
    """Request model for sending an authentication frame."""
    session_id: str
    frame: str  # base64-encoded image


class AuthFrameResponse(BaseModel):
    """Response model for frame processing."""
    session_id: str
    current_challenge: str
    progress: str  # e.g., "2/3 challenges completed"
    detail: str


class FinishAuthRequest(BaseModel):
    """Request model for finishing authentication."""
    session_id: str


class FinishAuthResponse(BaseModel):
    """Response model for authentication decision."""
    decision: str  # "allow" or "deny"
    reason_codes: List[str]
    liveness_passed: bool
    similarity_score: Optional[float] = None


@router.post("/start", response_model=StartAuthResponse)
async def start_authentication(request: StartAuthRequest) -> StartAuthResponse:
    """
    Start an authentication session with randomized liveness challenges.

    Returns:
        - session_id: Unique session identifier
        - challenges: List of challenges to complete (randomized order)
    """
    try:
        # Generate randomized challenges
        challenges_list = _challenge_generator.generate_challenges()

        # Create session with challenges
        session = _session_store.create_session(challenges_list)

        # Reset detectors for new session
        _liveness_evaluator.reset_detectors()

        # Return challenge names to client
        challenge_names = [c.challenge_type.value for c in challenges_list]

        return StartAuthResponse(
            session_id=session.session_id,
            challenges=challenge_names,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start authentication: {str(e)}",
        )


@router.post("/frame", response_model=AuthFrameResponse)
async def auth_frame(request: AuthFrameRequest) -> AuthFrameResponse:
    """
    Process a frame for the current challenge.

    Accepts a base64-encoded image and evaluates it against the current challenge.

    Returns:
        - session_id: The session identifier
        - current_challenge: Name of the current challenge
        - progress: String showing completion progress
        - detail: Detailed message about frame processing result
    """
    try:
        # Get session
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

        # Detect face and extract landmarks
        face_detected, landmarks, detection_metadata = _face_detector.detect_and_extract_landmarks(
            request.frame
        )

        if not face_detected:
            return AuthFrameResponse(
                session_id=session.session_id,
                current_challenge=session.get_current_challenge().challenge_type.value if session.get_current_challenge() else "none",
                progress=f"{sum(1 for c in session.challenges if c.completed)}/{len(session.challenges)} challenges",
                detail="No face detected in frame",
            )

        # Process frame against current challenge
        challenge_completed, detail_msg = _liveness_evaluator.process_frame(
            session, request.frame, landmarks
        )

        # If challenge completed, move to next
        if challenge_completed:
            if session.has_next_challenge():
                session.move_to_next_challenge()
                _liveness_evaluator.reset_detectors()
                detail_msg += " Moving to next challenge..."
            else:
                # All challenges done, evaluate
                _liveness_evaluator.evaluate_session_result(session)

        # Save session
        _session_store.save_session(session)

        # Return progress
        progress = f"{sum(1 for c in session.challenges if c.completed)}/{len(session.challenges)} challenges"
        next_challenge = session.get_current_challenge()

        return AuthFrameResponse(
            session_id=session.session_id,
            current_challenge=next_challenge.challenge_type.value if next_challenge else "finished",
            progress=progress,
            detail=detail_msg,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Frame processing error: {str(e)}",
        )


@router.post("/finish", response_model=FinishAuthResponse)
async def finish_authentication(request: FinishAuthRequest) -> FinishAuthResponse:
    """
    Finish the authentication session and get the final decision.

    Applies the policy engine to determine allow/deny based on liveness result.

    Returns:
        - decision: "allow" or "deny"
        - reason_codes: List of reason codes
        - liveness_passed: Whether liveness verification passed
        - similarity_score: Optional similarity to enrolled template (future use)
    """
    try:
        # Get session
        session = _session_store.get_session(request.session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found or expired",
            )

        # Evaluate session with policy engine
        auth_decision = _policy_engine.evaluate(session)

        # Mark session as finished
        session.finished = True
        session.decision = auth_decision.decision
        session.reason_codes = auth_decision.reason_codes
        session.liveness_passed = auth_decision.liveness_passed
        session.similarity_score = auth_decision.similarity_score

        _session_store.save_session(session)

        return FinishAuthResponse(
            decision=auth_decision.decision,
            reason_codes=auth_decision.reason_codes,
            liveness_passed=auth_decision.liveness_passed,
            similarity_score=auth_decision.similarity_score,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error finishing authentication: {str(e)}",
        )

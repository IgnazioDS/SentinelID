"""
Reason codes for authentication decisions.
"""
from enum import Enum


class ReasonCode(str, Enum):
    """Enumeration of reason codes for auth decisions."""

    # Success
    SUCCESS = "SUCCESS"
    LIVENESS_PASSED = "LIVENESS_PASSED"

    # Liveness failures
    LIVENESS_FAILED = "LIVENESS_FAILED"
    CHALLENGE_TIMEOUT = "CHALLENGE_TIMEOUT"
    BLINK_NOT_DETECTED = "BLINK_NOT_DETECTED"
    HEAD_TURN_NOT_DETECTED = "HEAD_TURN_NOT_DETECTED"

    # Face detection issues
    NO_FACE_DETECTED = "NO_FACE_DETECTED"
    MULTIPLE_FACES_DETECTED = "MULTIPLE_FACES_DETECTED"
    FACE_TOO_SMALL = "FACE_TOO_SMALL"
    FACE_TOO_LARGE = "FACE_TOO_LARGE"
    FACE_NOT_CENTERED = "FACE_NOT_CENTERED"

    # Quality issues
    LOW_IMAGE_QUALITY = "LOW_IMAGE_QUALITY"
    POOR_LIGHTING = "POOR_LIGHTING"
    FACE_OBSCURED = "FACE_OBSCURED"

    # Session issues
    INVALID_SESSION = "INVALID_SESSION"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    SESSION_ALREADY_FINISHED = "SESSION_ALREADY_FINISHED"

    # Other errors
    INTERNAL_ERROR = "INTERNAL_ERROR"

    # Verification / enrollment lifecycle (v0.8)
    NOT_ENROLLED = "NOT_ENROLLED"
    SIMILARITY_BELOW_THRESHOLD = "SIMILARITY_BELOW_THRESHOLD"
    NO_FACE = "NO_FACE"
    MULTIPLE_FACES = "MULTIPLE_FACES"
    LOW_QUALITY = "LOW_QUALITY"
    POSE_TOO_LARGE = "POSE_TOO_LARGE"
    TOO_DARK = "TOO_DARK"
    TOO_BLURRY = "TOO_BLURRY"
    ENROLL_INCOMPLETE = "ENROLL_INCOMPLETE"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    FALLBACK_EMBEDDING_USED = "FALLBACK_EMBEDDING_USED"

    # Risk scoring (v0.7)
    RISK_HIGH = "RISK_HIGH"
    RISK_STEP_UP = "RISK_STEP_UP"
    SPOOF_SUSPECT_SCREEN = "SPOOF_SUSPECT_SCREEN"
    SPOOF_SUSPECT_TEMPORAL = "SPOOF_SUSPECT_TEMPORAL"
    SPOOF_SUSPECT_BOUNDARY = "SPOOF_SUSPECT_BOUNDARY"

    # Step-up flow (v0.7)
    STEP_UP_REQUIRED = "STEP_UP_REQUIRED"
    STEP_UP_COMPLETED = "STEP_UP_COMPLETED"
    STEP_UP_FAILED = "STEP_UP_FAILED"
    MAX_STEP_UPS_REACHED = "MAX_STEP_UPS_REACHED"


def get_reason_messages() -> dict:
    """Return human-readable messages for reason codes."""
    return {
        ReasonCode.SUCCESS: "Authentication successful",
        ReasonCode.LIVENESS_PASSED: "All liveness challenges passed",
        ReasonCode.LIVENESS_FAILED: "Liveness verification failed",
        ReasonCode.CHALLENGE_TIMEOUT: "Challenge took too long to complete",
        ReasonCode.BLINK_NOT_DETECTED: "Blink was not detected within the time window",
        ReasonCode.HEAD_TURN_NOT_DETECTED: "Head turn was not detected within the time window",
        ReasonCode.NO_FACE_DETECTED: "No face detected in the frame",
        ReasonCode.MULTIPLE_FACES_DETECTED: "Multiple faces detected; only one person allowed",
        ReasonCode.FACE_TOO_SMALL: "Face is too small in the frame",
        ReasonCode.FACE_TOO_LARGE: "Face is too large in the frame",
        ReasonCode.FACE_NOT_CENTERED: "Face is not properly centered",
        ReasonCode.LOW_IMAGE_QUALITY: "Image quality is too low",
        ReasonCode.POOR_LIGHTING: "Lighting conditions are poor",
        ReasonCode.FACE_OBSCURED: "Face is obscured or partially hidden",
        ReasonCode.INVALID_SESSION: "Invalid or non-existent session",
        ReasonCode.SESSION_EXPIRED: "Session has expired",
        ReasonCode.SESSION_ALREADY_FINISHED: "Session has already been finished",
        ReasonCode.INTERNAL_ERROR: "Internal service error",
        ReasonCode.NOT_ENROLLED: "No enrolled biometric template found",
        ReasonCode.SIMILARITY_BELOW_THRESHOLD: "Face similarity is below verification threshold",
        ReasonCode.NO_FACE: "No face was detected",
        ReasonCode.MULTIPLE_FACES: "Multiple faces detected",
        ReasonCode.LOW_QUALITY: "Face sample quality is insufficient",
        ReasonCode.POSE_TOO_LARGE: "Face pose angle is outside the allowed limits",
        ReasonCode.TOO_DARK: "Face sample is too dark",
        ReasonCode.TOO_BLURRY: "Face sample is too blurry",
        ReasonCode.ENROLL_INCOMPLETE: "Enrollment does not yet have enough good frames",
        ReasonCode.MODEL_UNAVAILABLE: "Face model is unavailable",
        ReasonCode.FALLBACK_EMBEDDING_USED: "Fallback embedding path was used",
        # Risk / spoof
        ReasonCode.RISK_HIGH: "Risk score exceeds denial threshold",
        ReasonCode.RISK_STEP_UP: "Risk score requires additional verification",
        ReasonCode.SPOOF_SUSPECT_SCREEN: "Screen replay artefacts detected",
        ReasonCode.SPOOF_SUSPECT_TEMPORAL: "Abnormal temporal motion pattern detected",
        ReasonCode.SPOOF_SUSPECT_BOUNDARY: "Unnatural face boundary sharpness detected",
        # Step-up
        ReasonCode.STEP_UP_REQUIRED: "Step-up verification required",
        ReasonCode.STEP_UP_COMPLETED: "Step-up verification completed",
        ReasonCode.STEP_UP_FAILED: "Step-up verification failed",
        ReasonCode.MAX_STEP_UPS_REACHED: "Maximum step-up attempts reached",
    }

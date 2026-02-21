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
    }

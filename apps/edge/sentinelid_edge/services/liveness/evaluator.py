"""
Liveness evaluator that processes frames against active challenges.
"""
import base64
import numpy as np
from typing import Optional, Tuple, Dict
from io import BytesIO
from ...domain.models import AuthSession, Challenge, ChallengeType
from ...domain.reasons import ReasonCode
from .blink import BlinkDetector
from .pose import HeadPoseDetector


class LivenessEvaluator:
    """
    Evaluates liveness by processing video frames against active challenges.
    """

    def __init__(self):
        self.blink_detector = BlinkDetector()
        self.pose_detector = HeadPoseDetector()

    def process_frame(
        self,
        session: AuthSession,
        frame_data: str,  # base64-encoded image
        landmarks: Optional[np.ndarray] = None,
        use_step_up: bool = False,
    ) -> Tuple[bool, str]:
        """
        Process a frame for the current challenge in a session.

        Args:
            session: The authentication session
            frame_data: Base64-encoded frame image (may be decoded in future)
            landmarks: Facial landmarks as Nx2 array (if available from detector)
            use_step_up: When True, process against step-up challenges instead
                         of primary challenges.

        Returns:
            (challenge_completed, detail_message)
        """
        if use_step_up:
            current_challenge = session.get_current_step_up_challenge()
        else:
            current_challenge = session.get_current_challenge()

        if not current_challenge:
            return False, "No active challenge"

        if current_challenge.is_expired():
            current_challenge.completed = True
            current_challenge.passed = False
            session.reason_codes.append(ReasonCode.CHALLENGE_TIMEOUT)
            return True, "Challenge timed out"

        # Process based on challenge type
        challenge_passed = False
        if current_challenge.challenge_type == ChallengeType.BLINK:
            blink_detected, ear = self.blink_detector.update(landmarks)
            if blink_detected:
                challenge_passed = True
        elif current_challenge.challenge_type == ChallengeType.TURN_LEFT:
            turn_detected, yaw, direction = self.pose_detector.update(landmarks)
            if turn_detected and direction == "left":
                challenge_passed = True
        elif current_challenge.challenge_type == ChallengeType.TURN_RIGHT:
            turn_detected, yaw, direction = self.pose_detector.update(landmarks)
            if turn_detected and direction == "right":
                challenge_passed = True

        if challenge_passed:
            current_challenge.completed = True
            current_challenge.passed = True
            return True, f"Challenge passed: {current_challenge.challenge_type}"

        return False, "Challenge in progress..."

    def evaluate_session_result(self, session: AuthSession) -> bool:
        """
        Determine if all challenges were passed.

        When session.in_step_up is True, evaluates step-up challenges;
        otherwise evaluates primary challenges.

        Returns:
            True if all relevant challenges passed, False otherwise.
        """
        if session.in_step_up:
            if not session.all_step_up_challenges_completed():
                return False
            all_passed = all(c.passed for c in session.step_up_challenges)
        else:
            if not session.all_challenges_completed():
                return False
            all_passed = all(c.passed for c in session.challenges)

        if all_passed:
            session.liveness_passed = True
            if ReasonCode.LIVENESS_FAILED not in session.reason_codes:
                session.reason_codes.append(ReasonCode.LIVENESS_PASSED)
        else:
            session.liveness_passed = False
            if ReasonCode.LIVENESS_FAILED not in session.reason_codes:
                session.reason_codes.append(ReasonCode.LIVENESS_FAILED)

        return all_passed

    def reset_detectors(self) -> None:
        """Reset all detectors for a new session."""
        self.blink_detector.reset()
        self.pose_detector.reset()

    def get_detector_state(self) -> Dict:
        """Get current state of all detectors for debugging."""
        return {
            "blink": {
                "count": self.blink_detector.get_blink_count(),
                "history_length": len(self.blink_detector.eye_aspect_ratio_history),
            },
            "pose": {
                "left_turns": self.pose_detector.get_left_turn_count(),
                "right_turns": self.pose_detector.get_right_turn_count(),
                "current_state": self.pose_detector.turn_state,
            },
        }

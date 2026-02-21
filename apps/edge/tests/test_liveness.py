"""
Unit tests for liveness detection and evaluation.
"""
import pytest
import numpy as np
from sentinelid_edge.services.liveness.blink import BlinkDetector
from sentinelid_edge.services.liveness.pose import HeadPoseDetector
from sentinelid_edge.services.liveness.challenges import SessionStore, ChallengeGenerator
from sentinelid_edge.services.liveness.evaluator import LivenessEvaluator
from sentinelid_edge.domain.models import Challenge, ChallengeType, AuthSession


class TestBlinkDetector:
    """Test blink detection using Eye Aspect Ratio."""

    def setup_method(self):
        """Set up test fixtures."""
        self.detector = BlinkDetector()

    def test_blink_detector_initialization(self):
        """Test that blink detector initializes correctly."""
        assert self.detector.blink_count == 0
        assert self.detector.eyes_closed_count == 0
        assert len(self.detector.eye_aspect_ratio_history) == 0

    def test_update_with_none_landmarks(self):
        """Test handling of None landmarks."""
        blink_detected, ear = self.detector.update(None)
        assert not blink_detected
        assert ear == 0.0

    def test_update_with_empty_landmarks(self):
        """Test handling of empty landmarks array."""
        landmarks = np.array([])
        blink_detected, ear = self.detector.update(landmarks)
        assert not blink_detected
        assert ear == 0.0

    def test_eyes_open_detection(self):
        """Test detection of open eyes."""
        # Create landmarks for open eyes (high EAR)
        landmarks = self._create_open_eyes_landmarks()
        blink_detected, ear = self.detector.update(landmarks)
        assert not blink_detected
        assert ear > 0.2  # EAR threshold is 0.2

    def test_eyes_closed_detection(self):
        """Test detection of closed eyes."""
        # Create landmarks for closed eyes (low EAR)
        landmarks = self._create_closed_eyes_landmarks()
        blink_detected, ear = self.detector.update(landmarks)
        assert not blink_detected
        assert ear < 0.2

    def test_blink_detection_sequence(self):
        """Test complete blink sequence (open -> closed -> open)."""
        # Start with open eyes
        for _ in range(3):
            landmarks = self._create_open_eyes_landmarks()
            blink_detected, _ = self.detector.update(landmarks)
            assert not blink_detected

        # Close eyes
        for _ in range(3):
            landmarks = self._create_closed_eyes_landmarks()
            blink_detected, _ = self.detector.update(landmarks)
            assert not blink_detected

        # Open eyes again (should detect blink)
        for i in range(10):
            landmarks = self._create_open_eyes_landmarks()
            blink_detected, _ = self.detector.update(landmarks)
            if i >= 2:  # Should be True after debounce
                assert blink_detected
                break

    def test_reset_clears_state(self):
        """Test that reset clears detector state."""
        self.detector.blink_count = 5
        self.detector.reset()
        assert self.detector.blink_count == 0
        assert len(self.detector.eye_aspect_ratio_history) == 0

    @staticmethod
    def _create_open_eyes_landmarks():
        """Create mock landmarks for open eyes."""
        landmarks = np.zeros((68, 2))
        # Set eye points to indicate open eyes (wider vertical distance)
        landmarks[36:42, 0] = [100, 110, 120, 130, 120, 110]  # Left eye
        landmarks[36:42, 1] = [50, 40, 40, 50, 60, 60]  # Open (larger vertical)
        landmarks[42:48, 0] = [140, 150, 160, 170, 160, 150]  # Right eye
        landmarks[42:48, 1] = [50, 40, 40, 50, 60, 60]  # Open
        return landmarks

    @staticmethod
    def _create_closed_eyes_landmarks():
        """Create mock landmarks for closed eyes."""
        landmarks = np.zeros((68, 2))
        # Set eye points to indicate closed eyes (smaller vertical distance)
        landmarks[36:42, 0] = [100, 110, 120, 130, 120, 110]  # Left eye
        landmarks[36:42, 1] = [50, 48, 48, 50, 52, 52]  # Closed (smaller vertical)
        landmarks[42:48, 0] = [140, 150, 160, 170, 160, 150]  # Right eye
        landmarks[42:48, 1] = [50, 48, 48, 50, 52, 52]  # Closed
        return landmarks


class TestHeadPoseDetector:
    """Test head pose and turn detection."""

    def setup_method(self):
        """Set up test fixtures."""
        self.detector = HeadPoseDetector()

    def test_pose_detector_initialization(self):
        """Test that pose detector initializes correctly."""
        assert self.detector.left_turn_count == 0
        assert self.detector.right_turn_count == 0
        assert self.detector.turn_state == "neutral"

    def test_update_with_none_landmarks(self):
        """Test handling of None landmarks."""
        turn_detected, yaw, direction = self.detector.update(None)
        assert not turn_detected
        assert yaw == 0.0
        assert direction == "neutral"

    def test_neutral_pose(self):
        """Test detection of neutral head pose."""
        landmarks = self._create_neutral_landmarks()
        turn_detected, yaw, direction = self.detector.update(landmarks)
        assert direction == "neutral"
        assert yaw > -15 and yaw < 15

    def test_left_turn_detection(self):
        """Test detection of left head turn."""
        for _ in range(6):
            landmarks = self._create_left_turn_landmarks()
            turn_detected, yaw, direction = self.detector.update(landmarks)
            assert yaw < -15
            assert direction == "left"
            if _>= 5:
                assert turn_detected

    def test_right_turn_detection(self):
        """Test detection of right head turn."""
        for _ in range(6):
            landmarks = self._create_right_turn_landmarks()
            turn_detected, yaw, direction = self.detector.update(landmarks)
            assert yaw > 15
            assert direction == "right"

    def test_complete_turn_sequence(self):
        """Test complete turn sequence (neutral -> left -> neutral)."""
        # Start neutral
        landmarks = self._create_neutral_landmarks()
        self.detector.update(landmarks)

        # Turn left
        for _ in range(6):
            landmarks = self._create_left_turn_landmarks()
            turn_detected, _, _ = self.detector.update(landmarks)

        # Return to neutral (should detect turn)
        for _ in range(6):
            landmarks = self._create_neutral_landmarks()
            turn_detected, _, direction = self.detector.update(landmarks)
            if direction == "neutral":
                # Turn should be detected
                assert self.detector.left_turn_count > 0

    def test_reset_clears_state(self):
        """Test that reset clears detector state."""
        self.detector.left_turn_count = 3
        self.detector.right_turn_count = 2
        self.detector.reset()
        assert self.detector.left_turn_count == 0
        assert self.detector.right_turn_count == 0

    @staticmethod
    def _create_neutral_landmarks():
        """Create mock landmarks for neutral head pose."""
        landmarks = np.zeros((68, 2))
        # Nose at center
        landmarks[30] = [200, 300]  # Nose tip
        # Eyes centered
        landmarks[36:42, 0] = [150, 160, 170, 180, 170, 160]  # Left eye x
        landmarks[42:48, 0] = [220, 230, 240, 250, 240, 230]  # Right eye x
        landmarks[36:48, 1] = [250] * 12  # Both eyes at same y
        return landmarks

    @staticmethod
    def _create_left_turn_landmarks():
        """Create mock landmarks for left head turn."""
        landmarks = np.zeros((68, 2))
        # Nose turned left (smaller x)
        landmarks[30] = [150, 300]  # Nose tip (turned left)
        # Eyes stay more centered
        landmarks[36:42, 0] = [160, 170, 180, 190, 180, 170]  # Left eye x
        landmarks[42:48, 0] = [230, 240, 250, 260, 250, 240]  # Right eye x
        landmarks[36:48, 1] = [250] * 12
        return landmarks

    @staticmethod
    def _create_right_turn_landmarks():
        """Create mock landmarks for right head turn."""
        landmarks = np.zeros((68, 2))
        # Nose turned right (larger x)
        landmarks[30] = [250, 300]  # Nose tip (turned right)
        # Eyes stay more centered
        landmarks[36:42, 0] = [160, 170, 180, 190, 180, 170]  # Left eye x
        landmarks[42:48, 0] = [230, 240, 250, 260, 250, 240]  # Right eye x
        landmarks[36:48, 1] = [250] * 12
        return landmarks


class TestSessionStore:
    """Test session management."""

    def setup_method(self):
        """Set up test fixtures."""
        self.store = SessionStore(session_timeout_seconds=120)

    def test_create_session(self):
        """Test session creation."""
        challenges = [Challenge(ChallengeType.BLINK)]
        session = self.store.create_session(challenges)
        assert session.session_id is not None
        assert len(session.challenges) == 1
        assert not session.finished

    def test_get_session(self):
        """Test session retrieval."""
        challenges = [Challenge(ChallengeType.BLINK)]
        created = self.store.create_session(challenges)
        retrieved = self.store.get_session(created.session_id)
        assert retrieved is not None
        assert retrieved.session_id == created.session_id

    def test_get_nonexistent_session(self):
        """Test retrieval of nonexistent session."""
        session = self.store.get_session("nonexistent-id")
        assert session is None

    def test_save_session(self):
        """Test session updates."""
        challenges = [Challenge(ChallengeType.BLINK)]
        session = self.store.create_session(challenges)
        session.finished = True
        self.store.save_session(session)
        retrieved = self.store.get_session(session.session_id)
        assert retrieved.finished


class TestChallengeGenerator:
    """Test challenge generation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.generator = ChallengeGenerator()

    def test_generate_challenges(self):
        """Test that challenges are generated."""
        challenges = self.generator.generate_challenges()
        assert len(challenges) >= 2
        assert len(challenges) <= 3

    def test_challenges_are_randomized(self):
        """Test that multiple generations produce different orders."""
        challenges_1 = self.generator.generate_challenges()
        challenges_2 = self.generator.generate_challenges()
        # At least some should be different (with high probability)
        orders_different = any(
            c1.challenge_type != c2.challenge_type
            for c1, c2 in zip(challenges_1, challenges_2)
        )
        assert orders_different

    def test_challenge_types_valid(self):
        """Test that all generated challenges are valid types."""
        for _ in range(10):
            challenges = self.generator.generate_challenges()
            for challenge in challenges:
                assert challenge.challenge_type in [
                    ChallengeType.BLINK,
                    ChallengeType.TURN_LEFT,
                    ChallengeType.TURN_RIGHT,
                ]


class TestLivenessEvaluator:
    """Test liveness evaluator."""

    def setup_method(self):
        """Set up test fixtures."""
        self.evaluator = LivenessEvaluator()
        self.store = SessionStore()
        self.generator = ChallengeGenerator()

    def test_evaluator_initialization(self):
        """Test evaluator initializes correctly."""
        assert self.evaluator.blink_detector is not None
        assert self.evaluator.pose_detector is not None

    def test_process_frame_without_challenge(self):
        """Test processing frame when no challenge is active."""
        challenges = []
        session = self.store.create_session(challenges)
        completed, msg = self.evaluator.process_frame(session, "frame_data", None)
        assert not completed

    def test_reset_detectors(self):
        """Test detector reset."""
        self.evaluator.blink_detector.blink_count = 5
        self.evaluator.pose_detector.left_turn_count = 3
        self.evaluator.reset_detectors()
        assert self.evaluator.blink_detector.blink_count == 0
        assert self.evaluator.pose_detector.left_turn_count == 0

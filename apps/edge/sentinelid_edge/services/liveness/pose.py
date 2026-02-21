"""
Head pose and turn detection using facial landmarks.
"""
import numpy as np
from typing import Optional, Tuple
from enum import Enum


class HeadTurnDirection(str, Enum):
    """Direction of head turn."""
    LEFT = "left"
    RIGHT = "right"
    NEUTRAL = "neutral"


class HeadPoseDetector:
    """Detects head turns (yaw) using facial landmarks."""

    # Yaw angle thresholds (in degrees)
    YAW_TURN_THRESHOLD = 15  # Degrees from center
    YAW_DEBOUNCE_FRAMES = 5  # Frames to confirm turn

    def __init__(self):
        self.yaw_history = []
        self.turn_state = "neutral"  # "neutral", "turning_left", "turning_right"
        self.frames_in_turn = 0
        self.left_turn_count = 0
        self.right_turn_count = 0

    def update(self, landmarks: Optional[np.ndarray]) -> Tuple[bool, float, str]:
        """
        Update head pose detector with new frame landmarks.

        Args:
            landmarks: Facial landmarks array (or None if no face detected)

        Returns:
            (turn_detected, yaw_angle, direction)
            - turn_detected: True if a head turn was completed
            - yaw_angle: Current yaw angle in degrees
            - direction: "left", "right", or "neutral"
        """
        turn_detected = False
        yaw = 0.0
        direction = "neutral"

        if landmarks is None or len(landmarks) == 0:
            self.frames_in_turn = 0
            self.turn_state = "neutral"
            return False, 0.0, "neutral"

        # Calculate yaw from landmarks
        try:
            yaw = self._calculate_yaw(landmarks)
        except (IndexError, ValueError):
            self.frames_in_turn = 0
            self.turn_state = "neutral"
            return False, 0.0, "neutral"

        self.yaw_history.append(yaw)

        # Determine current direction
        if yaw < -self.YAW_TURN_THRESHOLD:
            direction = "left"
        elif yaw > self.YAW_TURN_THRESHOLD:
            direction = "right"
        else:
            direction = "neutral"

        # State machine for turn detection
        if direction == "neutral":
            if self.turn_state in ["turning_left", "turning_right"]:
                # Just returned to neutral after a turn
                if self.frames_in_turn > self.YAW_DEBOUNCE_FRAMES:
                    turn_detected = True
                    if self.turn_state == "turning_left":
                        self.left_turn_count += 1
                    else:
                        self.right_turn_count += 1
            self.turn_state = "neutral"
            self.frames_in_turn = 0
        elif direction == "left":
            if self.turn_state != "turning_left":
                self.turn_state = "turning_left"
                self.frames_in_turn = 0
            else:
                self.frames_in_turn += 1
        elif direction == "right":
            if self.turn_state != "turning_right":
                self.turn_state = "turning_right"
                self.frames_in_turn = 0
            else:
                self.frames_in_turn += 1

        return turn_detected, yaw, direction

    def reset(self) -> None:
        """Reset detector state."""
        self.yaw_history = []
        self.turn_state = "neutral"
        self.frames_in_turn = 0
        self.left_turn_count = 0
        self.right_turn_count = 0

    def get_left_turn_count(self) -> int:
        """Get total left turns detected."""
        return self.left_turn_count

    def get_right_turn_count(self) -> int:
        """Get total right turns detected."""
        return self.right_turn_count

    def _calculate_yaw(self, landmarks: np.ndarray) -> float:
        """
        Calculate head yaw angle from facial landmarks.

        Uses nose and eye positions to estimate yaw.
        Returns angle in degrees: negative = turn left, positive = turn right
        """
        if len(landmarks) < 48:
            return 0.0

        try:
            # Nose tip (index 30 in 68-point format)
            nose = landmarks[30]

            # Left and right eye centers (approximately)
            left_eye = np.mean(landmarks[36:42], axis=0)
            right_eye = np.mean(landmarks[42:48], axis=0)

            # Calculate horizontal alignment
            eye_center_x = (left_eye[0] + right_eye[0]) / 2.0
            nose_x = nose[0]

            # Horizontal distance between nose and eye center
            # Positive = nose right of center = turn right
            # Negative = nose left of center = turn left
            dx = nose_x - eye_center_x

            # Eye distance for normalization
            eye_distance = np.linalg.norm(right_eye - left_eye)

            if eye_distance < 1:
                return 0.0

            # Simple yaw estimation (in degrees, roughly)
            # This is a simplified method; a more accurate one would use PnP
            yaw_normalized = dx / eye_distance
            yaw_degrees = np.degrees(np.arctan(yaw_normalized))

            return float(yaw_degrees)
        except Exception:
            return 0.0

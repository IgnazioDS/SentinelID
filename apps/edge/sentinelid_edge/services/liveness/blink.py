"""
Blink detection using Eye Aspect Ratio (EAR).
"""
import numpy as np
from typing import Optional, Tuple


class BlinkDetector:
    """Detects blinks using Eye Aspect Ratio calculated from facial landmarks."""

    # EAR thresholds
    EAR_THRESHOLD = 0.2  # Below this = eye closed
    EAR_CONSEC_FRAMES = 2  # Frames to confirm blink state
    DEBOUNCE_FRAMES = 5  # Frames between blinks

    def __init__(self):
        self.eye_aspect_ratio_history = []
        self.eyes_closed_count = 0
        self.blink_count = 0
        self.frames_since_blink = 0
        self.was_closed = False

    def update(self, landmarks: Optional[np.ndarray]) -> Tuple[bool, float]:
        """
        Update blink detector with new frame landmarks.

        Args:
            landmarks: Facial landmarks array (or None if no face detected)

        Returns:
            (blink_detected, eye_aspect_ratio)
            - blink_detected: True if a blink was just detected
            - eye_aspect_ratio: Current EAR value (0 if no face)
        """
        blink_detected = False
        ear = 0.0

        if landmarks is None or len(landmarks) == 0:
            self.eyes_closed_count = 0
            self.was_closed = False
            self.frames_since_blink += 1
            return False, 0.0

        # Calculate EAR from eye landmarks
        # Assuming landmarks contain eye points (indices for common detectors)
        try:
            ear = self._calculate_ear(landmarks)
        except (IndexError, ValueError):
            self.eyes_closed_count = 0
            self.was_closed = False
            self.frames_since_blink += 1
            return False, 0.0

        self.eye_aspect_ratio_history.append(ear)
        self.frames_since_blink += 1

        # Detect eye closure
        if ear < self.EAR_THRESHOLD:
            self.eyes_closed_count += 1
        else:
            self.eyes_closed_count = 0

        # Detect transition from closed to open (blink detected)
        is_closed = self.eyes_closed_count >= self.EAR_CONSEC_FRAMES
        if self.was_closed and not is_closed and self.frames_since_blink > self.DEBOUNCE_FRAMES:
            blink_detected = True
            self.blink_count += 1
            self.frames_since_blink = 0

        self.was_closed = is_closed
        return blink_detected, ear

    def reset(self) -> None:
        """Reset detector state."""
        self.eye_aspect_ratio_history = []
        self.eyes_closed_count = 0
        self.blink_count = 0
        self.frames_since_blink = 0
        self.was_closed = False

    def get_blink_count(self) -> int:
        """Get total blinks detected in current session."""
        return self.blink_count

    def _calculate_ear(self, landmarks: np.ndarray) -> float:
        """
        Calculate Eye Aspect Ratio.

        Assumes landmarks is a Nx2 array of (x, y) coordinates.
        For a typical face detector (68 points or MediaPipe):
        - Left eye: points 36-41 (68-point) or 33, 160, 158, 133, 153, 144 (MediaPipe)
        - Right eye: points 42-47 (68-point) or 362, 385, 387, 373, 380, 381 (MediaPipe)

        This is a simplified version using indices 36-47 (assumes 68-point landmark format).
        """
        if len(landmarks) < 48:
            # Not enough landmarks, return high EAR (eyes open)
            return 1.0

        # Left eye (indices 36-41 in 68-point format)
        left_eye = landmarks[36:42]

        # Right eye (indices 42-47 in 68-point format)
        right_eye = landmarks[42:48]

        # Calculate EAR for each eye
        left_ear = self._compute_eye_aspect_ratio(left_eye)
        right_ear = self._compute_eye_aspect_ratio(right_eye)

        # Average the two eyes
        ear = (left_ear + right_ear) / 2.0
        return float(ear)

    @staticmethod
    def _compute_eye_aspect_ratio(eye: np.ndarray) -> float:
        """
        Compute eye aspect ratio for a single eye.

        Eye is 6 points: outer-left, top-left, top-right, outer-right, bottom-right, bottom-left
        """
        if len(eye) != 6:
            return 1.0

        # Euclidean distances between eye points
        # Vertical distances
        A = np.linalg.norm(eye[1] - eye[4])
        B = np.linalg.norm(eye[2] - eye[3])

        # Horizontal distance
        C = np.linalg.norm(eye[0] - eye[5])

        # Aspect ratio
        ear = (A + B) / (2.0 * C)
        return float(ear)

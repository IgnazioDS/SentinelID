"""
Face detection and landmark extraction.
"""
import base64
import numpy as np
from typing import Optional, Tuple
from io import BytesIO


class FaceDetector:
    """
    Detects faces and extracts landmarks.

    In Phase 2, this is a stub using mock landmarks.
    In production, would integrate with insightface or MediaPipe.
    """

    def __init__(self):
        """Initialize face detector."""
        self.detector = None  # TODO: integrate insightface

    def detect_and_extract_landmarks(
        self, frame_data: str
    ) -> Tuple[bool, Optional[np.ndarray], dict]:
        """
        Detect face and extract landmarks from base64 frame.

        Args:
            frame_data: Base64-encoded image string

        Returns:
            (face_detected, landmarks, metadata)
            - face_detected: True if exactly one face detected
            - landmarks: Nx2 array of (x,y) coordinates or None
            - metadata: dict with detection details (num_faces, confidence, etc.)
        """
        try:
            # Decode base64 frame
            # Note: For now, we return mock landmarks for development
            # In production, this would:
            # 1. Decode the base64 image
            # 2. Use insightface to detect face and extract landmarks
            # 3. Return real landmarks

            # Mock implementation for development
            # Returns 68-point landmark format
            landmarks = self._get_mock_landmarks()
            metadata = {
                "num_faces": 1,
                "confidence": 0.95,
                "face_quality": "good",
            }
            return True, landmarks, metadata
        except Exception as e:
            return False, None, {"error": str(e)}

    def _get_mock_landmarks(self) -> np.ndarray:
        """Get mock 68-point facial landmarks for development."""
        # Return a placeholder 68-point landmark array (x, y coordinates)
        # These represent a neutral frontal face
        landmarks = np.array([
            [150, 50],   # 0 - outer left
            [160, 40],   # 1 - outer left upper
            [170, 35],   # 2 - top left
            [180, 35],   # 3 - top center
            [190, 35],   # 4 - top right
            [200, 40],   # 5 - outer right upper
            [210, 50],   # 6 - outer right
            [215, 60],   # 7 - right side
            [218, 70],   # 8 - right side lower
            [215, 80],   # 9 - right chin
            [200, 85],   # 10 - right jaw
            [180, 88],   # 11 - chin
            [160, 88],   # 12 - left jaw
            [140, 85],   # 13 - left chin
            [135, 80],   # 14 - left side lower
            [132, 70],   # 15 - left side
            [130, 60],   # 16 - left side
            [155, 55],   # 17 - left eyebrow start
            [165, 52],   # 18 - left eyebrow
            [175, 51],   # 19 - left eyebrow end
            [145, 58],   # 20 - left eye outer
            [160, 54],   # 21 - left eye upper inner
            [170, 54],   # 22 - left eye upper outer
            [180, 58],   # 23 - left eye outer
            [170, 62],   # 24 - left eye lower outer
            [160, 62],   # 25 - left eye lower inner
            [160, 58],   # 26 - left eye center
            [185, 55],   # 27 - right eyebrow start
            [195, 52],   # 28 - right eyebrow
            [205, 51],   # 29 - right eyebrow end
            [175, 70],   # 30 - nose tip
            [173, 75],   # 31 - nose bottom left
            [175, 76],   # 32 - nose bottom center
            [177, 75],   # 33 - nose bottom right
            [210, 58],   # 34 - right eye outer
            [225, 54],   # 35 - right eye upper inner
            [235, 54],   # 36 - right eye upper outer (NOTE: indices 36-41 are left eye in standard)
            [245, 58],   # 37 - right eye outer
            [235, 62],   # 38 - right eye lower outer
            [225, 62],   # 39 - right eye lower inner
            [225, 58],   # 40 - right eye center
            [245, 58],   # 41 - right eye outer
            [242, 62],   # 42 - right eye lower outer (NOTE: indices 42-47 are right eye)
            [232, 62],   # 43 - right eye lower inner
            [232, 58],   # 44 - right eye center
            [175, 80],   # 45 - mouth left
            [175, 85],   # 46 - mouth upper left
            [180, 88],   # 47 - mouth upper center
            [185, 85],   # 48 - mouth upper right
            [185, 80],   # 49 - mouth right
            [185, 82],   # 50 - mouth lower right
            [180, 85],   # 51 - mouth lower center
            [175, 82],   # 52 - mouth lower left
            [180, 83],   # 53 - mouth center
            [180, 83],   # 54 - mouth center
            [180, 83],   # 55 - mouth center
            [180, 83],   # 56 - mouth center
            [180, 83],   # 57 - mouth center
            [180, 83],   # 58 - mouth center
            [180, 83],   # 59 - mouth center
            [180, 83],   # 60 - mouth center
            [180, 83],   # 61 - mouth center
            [180, 83],   # 62 - mouth center
            [180, 83],   # 63 - mouth center
            [180, 83],   # 64 - mouth center
            [180, 83],   # 65 - mouth center
            [180, 83],   # 66 - mouth center
            [180, 83],   # 67 - mouth center
        ])
        return landmarks

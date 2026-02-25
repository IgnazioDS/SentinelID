"""
Face quality gates for enrollment and verification.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

import cv2
import numpy as np

from ...core.config import settings
from ...domain.reasons import ReasonCode
from .detector import DetectedFace


@dataclass
class QualityReport:
    passed: bool
    reason_codes: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)


class FaceQualityGate:
    """Compute deterministic quality checks before enrollment/verification."""

    def __init__(self) -> None:
        self.min_face_size_px = settings.MIN_FACE_SIZE_PX
        self.min_blur_variance = settings.MIN_BLUR_VARIANCE
        self.min_illumination_mean = settings.MIN_ILLUMINATION_MEAN
        self.max_illumination_mean = settings.MAX_ILLUMINATION_MEAN
        self.max_abs_yaw_deg = settings.MAX_ABS_YAW_DEG
        self.max_abs_pitch_deg = settings.MAX_ABS_PITCH_DEG
        self.max_abs_roll_deg = settings.MAX_ABS_ROLL_DEG

    def evaluate(
        self,
        image_bgr: np.ndarray,
        faces: List[DetectedFace],
    ) -> QualityReport:
        if not faces:
            return QualityReport(False, [ReasonCode.NO_FACE], {"num_faces": 0})
        if len(faces) > 1:
            return QualityReport(False, [ReasonCode.MULTIPLE_FACES], {"num_faces": len(faces)})

        face = faces[0]
        x1, y1, x2, y2 = face.bbox
        width = float(max(1.0, x2 - x1))
        height = float(max(1.0, y2 - y1))
        face_size = float(min(width, height))

        h, w = image_bgr.shape[:2]
        ix1 = int(max(0, min(w - 1, x1)))
        iy1 = int(max(0, min(h - 1, y1)))
        ix2 = int(max(ix1 + 1, min(w, x2)))
        iy2 = int(max(iy1 + 1, min(h, y2)))
        crop = image_bgr[iy1:iy2, ix1:ix2]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

        blur_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        illum_mean = float(np.mean(gray))

        reasons: List[str] = []
        if face_size < self.min_face_size_px:
            reasons.append(ReasonCode.FACE_TOO_SMALL)
        if abs(face.yaw) > self.max_abs_yaw_deg or abs(face.pitch) > self.max_abs_pitch_deg or abs(face.roll) > self.max_abs_roll_deg:
            reasons.append(ReasonCode.POSE_TOO_LARGE)
        if blur_var < self.min_blur_variance:
            reasons.append(ReasonCode.TOO_BLURRY)
        if illum_mean < self.min_illumination_mean:
            reasons.append(ReasonCode.TOO_DARK)
        if illum_mean > self.max_illumination_mean:
            reasons.append(ReasonCode.LOW_QUALITY)

        deduped: List[str] = []
        seen = set()
        for code in reasons:
            if code not in seen:
                seen.add(code)
                deduped.append(code)

        return QualityReport(
            passed=len(deduped) == 0,
            reason_codes=deduped,
            metrics={
                "num_faces": 1,
                "face_size_px": round(face_size, 2),
                "blur_variance": round(blur_var, 4),
                "illumination_mean": round(illum_mean, 4),
                "pose": {
                    "yaw": round(float(face.yaw), 4),
                    "pitch": round(float(face.pitch), 4),
                    "roll": round(float(face.roll), 4),
                },
            },
        )

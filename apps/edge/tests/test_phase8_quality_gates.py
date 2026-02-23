"""Phase 8 quality gate unit tests."""

import numpy as np

from sentinelid_edge.domain.reasons import ReasonCode
from sentinelid_edge.services.vision.detector import DetectedFace
from sentinelid_edge.services.vision.quality import FaceQualityGate


def _face(yaw: float = 0.0) -> DetectedFace:
    return DetectedFace(
        bbox=(40.0, 30.0, 160.0, 170.0),
        landmarks=np.zeros((68, 2), dtype=np.float32),
        confidence=0.9,
        yaw=yaw,
        pitch=0.0,
        roll=0.0,
    )


def test_quality_gate_rejects_no_face() -> None:
    gate = FaceQualityGate()
    image = np.full((200, 200, 3), 128, dtype=np.uint8)
    report = gate.evaluate(image, [])
    assert report.passed is False
    assert report.reason_codes == [ReasonCode.NO_FACE]


def test_quality_gate_rejects_multiple_faces() -> None:
    gate = FaceQualityGate()
    image = np.full((200, 200, 3), 128, dtype=np.uint8)
    report = gate.evaluate(image, [_face(), _face()])
    assert report.passed is False
    assert report.reason_codes == [ReasonCode.MULTIPLE_FACES]


def test_quality_gate_rejects_too_dark() -> None:
    gate = FaceQualityGate()
    gate.min_blur_variance = 0.0
    image = np.zeros((200, 200, 3), dtype=np.uint8)
    report = gate.evaluate(image, [_face()])
    assert report.passed is False
    assert ReasonCode.TOO_DARK in report.reason_codes
    assert ReasonCode.LOW_QUALITY in report.reason_codes


def test_quality_gate_rejects_too_blurry() -> None:
    gate = FaceQualityGate()
    gate.min_blur_variance = 999999.0
    gate.min_illumination_mean = 0.0
    image = np.full((200, 200, 3), 120, dtype=np.uint8)
    report = gate.evaluate(image, [_face()])
    assert report.passed is False
    assert ReasonCode.TOO_BLURRY in report.reason_codes


def test_quality_gate_rejects_large_pose() -> None:
    gate = FaceQualityGate()
    gate.min_blur_variance = 0.0
    gate.min_illumination_mean = 0.0
    image = np.full((200, 200, 3), 160, dtype=np.uint8)
    report = gate.evaluate(image, [_face(yaw=45.0)])
    assert report.passed is False
    assert ReasonCode.POSE_TOO_LARGE in report.reason_codes


def test_quality_gate_accepts_good_frame() -> None:
    gate = FaceQualityGate()
    gate.min_blur_variance = 10.0
    gate.min_illumination_mean = 20.0
    rng = np.random.default_rng(42)
    image = rng.integers(0, 255, size=(200, 200, 3), dtype=np.uint8)
    report = gate.evaluate(image, [_face()])
    assert report.passed is True
    assert report.reason_codes == []
    assert report.metrics["num_faces"] == 1

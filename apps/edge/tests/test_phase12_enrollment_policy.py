"""v1.2 enrollment, quality, and policy precedence tests."""

from __future__ import annotations

import numpy as np

from sentinelid_edge.domain.models import AuthSession, Challenge, ChallengeType
from sentinelid_edge.domain.policy import PolicyEngine
from sentinelid_edge.domain.reasons import ReasonCode
from sentinelid_edge.services.enrollment.sessions import (
    EnrollmentPipeline,
    EnrollmentSession,
    EnrollmentSessionStore,
)
from sentinelid_edge.services.vision.detector import DetectedFace
from sentinelid_edge.services.vision.quality import FaceQualityGate, QualityReport


class _FakeDetector:
    def __init__(self, faces, image, model_unavailable=False):
        self._faces = faces
        self._image = image
        self._model_unavailable = model_unavailable

    def detect_faces(self, _frame_data):
        return self._faces, {
            "image_bgr": self._image,
            "model_unavailable": self._model_unavailable,
        }


class _FakeEmbedder:
    def __init__(self, embedding=None, fallback_used=False):
        self._embedding = embedding if embedding is not None else np.ones(512, dtype=np.float32)
        self.last_fallback_used = fallback_used

    def extract_embedding(self, _frame_data, face=None, image_bgr=None):
        return self._embedding


class _FakeQualityGate:
    def __init__(self, passed=True, reason_codes=None):
        self._passed = passed
        self._reason_codes = reason_codes or []

    def evaluate(self, _image, faces):
        return QualityReport(
            passed=self._passed,
            reason_codes=self._reason_codes,
            metrics={"num_faces": len(faces)},
        )


class _FakeRepo:
    def __init__(self):
        self.deleted = False
        self.stored = None

    def delete_all_templates(self):
        self.deleted = True

    def store_template(self, label, embedding):
        self.stored = (label, embedding)
        return "template-1"


def _face() -> DetectedFace:
    return DetectedFace(
        bbox=(20.0, 20.0, 120.0, 120.0),
        landmarks=np.zeros((68, 2), dtype=np.float32),
        confidence=0.9,
    )


def _completed_session(liveness_passed: bool = True) -> AuthSession:
    challenge = Challenge(ChallengeType.BLINK)
    challenge.completed = True
    challenge.passed = liveness_passed
    return AuthSession(
        session_id="s",
        challenges=[challenge],
        liveness_passed=liveness_passed,
    )


def test_enrollment_pipeline_rejects_model_unavailable() -> None:
    pipeline = EnrollmentPipeline(
        detector=_FakeDetector([_face()], np.full((150, 150, 3), 120, dtype=np.uint8), model_unavailable=True),
        embedder=_FakeEmbedder(),
        quality_gate=_FakeQualityGate(),
    )
    session = EnrollmentSession(session_id="s1", target_frames=2)

    result = pipeline.process_frame(session, "frame")
    assert result["accepted"] is False
    assert result["reason_codes"] == [ReasonCode.MODEL_UNAVAILABLE]


def test_enrollment_pipeline_marks_fallback_reason_when_used() -> None:
    pipeline = EnrollmentPipeline(
        detector=_FakeDetector([_face()], np.full((150, 150, 3), 120, dtype=np.uint8)),
        embedder=_FakeEmbedder(fallback_used=True),
        quality_gate=_FakeQualityGate(passed=True),
    )
    session = EnrollmentSession(session_id="s2", target_frames=2)

    result = pipeline.process_frame(session, "frame")
    assert result["accepted"] is True
    assert result["reason_codes"] == [ReasonCode.FALLBACK_EMBEDDING_USED]


def test_enrollment_pipeline_accepts_real_embedding_without_reason_codes() -> None:
    pipeline = EnrollmentPipeline(
        detector=_FakeDetector([_face()], np.full((150, 150, 3), 120, dtype=np.uint8)),
        embedder=_FakeEmbedder(fallback_used=False),
        quality_gate=_FakeQualityGate(passed=True),
    )
    session = EnrollmentSession(session_id="s3", target_frames=2)

    result = pipeline.process_frame(session, "frame")
    assert result["accepted"] is True
    assert result["reason_codes"] == []


def test_enrollment_build_template_returns_l2_normalized_mean() -> None:
    session = EnrollmentSession(session_id="s4", target_frames=2)
    session.embeddings = [
        np.ones(512, dtype=np.float32),
        np.ones(512, dtype=np.float32) * 0.5,
    ]
    pipeline = EnrollmentPipeline(
        detector=_FakeDetector([_face()], np.full((150, 150, 3), 120, dtype=np.uint8)),
        embedder=_FakeEmbedder(),
        quality_gate=_FakeQualityGate(passed=True),
    )

    template = pipeline.build_template(session)
    assert template.shape[0] == 512
    assert np.isclose(np.linalg.norm(template), 1.0, atol=1e-5)


def test_enrollment_commit_replaces_single_user_template() -> None:
    session = EnrollmentSession(session_id="s5", target_frames=2)
    session.embeddings = [
        np.ones(512, dtype=np.float32),
        np.ones(512, dtype=np.float32),
    ]
    repo = _FakeRepo()

    template_id, _template = EnrollmentPipeline.commit_template(session, "default", repo)

    assert template_id == "template-1"
    assert repo.deleted is True
    assert repo.stored[0] == "default"


def test_enrollment_session_store_expires_old_sessions() -> None:
    store = EnrollmentSessionStore(timeout_seconds=120)
    session = store.create_session(target_frames=3)
    session.created_at = 0.0
    store.save_session(session)

    assert store.get_session(session.session_id) is None


def test_quality_gate_uses_face_too_small_code() -> None:
    gate = FaceQualityGate()
    gate.min_blur_variance = 0.0
    gate.min_illumination_mean = 0.0
    image = np.full((200, 200, 3), 150, dtype=np.uint8)
    small_face = DetectedFace(
        bbox=(80.0, 80.0, 110.0, 110.0),
        landmarks=np.zeros((68, 2), dtype=np.float32),
        confidence=0.9,
    )

    report = gate.evaluate(image, [small_face])
    assert report.passed is False
    assert ReasonCode.FACE_TOO_SMALL in report.reason_codes


def test_policy_boundary_risk_equal_r1_is_step_up() -> None:
    engine = PolicyEngine(similarity_threshold=0.6, risk_threshold_r1=0.4, risk_threshold_r2=0.7)
    session = _completed_session(liveness_passed=True)

    decision = engine.evaluate(
        session,
        template_enrolled=True,
        similarity_score=0.95,
        enforce_similarity=True,
        risk_score=0.4,
    )
    assert decision.decision == "step_up"


def test_policy_boundary_risk_equal_r2_is_deny() -> None:
    engine = PolicyEngine(similarity_threshold=0.6, risk_threshold_r1=0.4, risk_threshold_r2=0.7)
    session = _completed_session(liveness_passed=True)

    decision = engine.evaluate(
        session,
        template_enrolled=True,
        similarity_score=0.95,
        enforce_similarity=True,
        risk_score=0.7,
    )
    assert decision.decision == "deny"
    assert ReasonCode.RISK_HIGH in decision.reason_codes


def test_policy_not_enrolled_has_highest_precedence() -> None:
    engine = PolicyEngine(similarity_threshold=0.6, risk_threshold_r1=0.4, risk_threshold_r2=0.7)
    session = _completed_session(liveness_passed=False)

    decision = engine.evaluate(
        session,
        template_enrolled=False,
        similarity_score=0.99,
        enforce_similarity=True,
        risk_score=0.99,
    )
    assert decision.decision == "deny"
    assert decision.reason_codes == [ReasonCode.NOT_ENROLLED]

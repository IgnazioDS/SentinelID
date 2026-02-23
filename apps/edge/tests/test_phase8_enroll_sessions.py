"""Phase 8 enrollment session + template aggregation behavior."""

import numpy as np
import pytest

from sentinelid_edge.domain.reasons import ReasonCode
from sentinelid_edge.services.enrollment.sessions import (
    EnrollmentPipeline,
    EnrollmentSession,
    EnrollmentSessionStore,
)
from sentinelid_edge.services.vision.detector import DetectedFace
from sentinelid_edge.services.vision.quality import QualityReport


class _FakeDetector:
    def __init__(self, faces, image):
        self._faces = faces
        self._image = image

    def detect_faces(self, _frame_data):
        return self._faces, {"image_bgr": self._image}


class _FakeEmbedder:
    def __init__(self, embedding=None):
        self._embedding = embedding if embedding is not None else np.ones(512, dtype=np.float32)

    def extract_embedding(self, _frame_data, face=None, image_bgr=None):
        return self._embedding


class _FakeQualityGate:
    def __init__(self, passed=True, reason_codes=None):
        self._passed = passed
        self._reason_codes = reason_codes or []

    def evaluate(self, image, faces):
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
        return 1

    def store_template(self, label, embedding):
        self.stored = (label, embedding)
        return "template-1"


def _face() -> DetectedFace:
    return DetectedFace(
        bbox=(20.0, 20.0, 120.0, 120.0),
        landmarks=np.zeros((68, 2), dtype=np.float32),
        confidence=0.9,
    )


def test_enrollment_session_store_create_get_delete() -> None:
    store = EnrollmentSessionStore(timeout_seconds=120)
    session = store.create_session(target_frames=5)
    assert store.get_session(session.session_id) is not None
    store.delete_session(session.session_id)
    assert store.get_session(session.session_id) is None


def test_enrollment_pipeline_accepts_frame() -> None:
    session = EnrollmentSession(session_id="s1", target_frames=3)
    pipeline = EnrollmentPipeline(
        detector=_FakeDetector([_face()], np.full((150, 150, 3), 120, dtype=np.uint8)),
        embedder=_FakeEmbedder(),
        quality_gate=_FakeQualityGate(passed=True),
    )

    result = pipeline.process_frame(session, "frame")
    assert result["accepted"] is True
    assert session.accepted_frames == 1


def test_enrollment_pipeline_rejects_low_quality() -> None:
    session = EnrollmentSession(session_id="s2", target_frames=3)
    pipeline = EnrollmentPipeline(
        detector=_FakeDetector([_face()], np.full((150, 150, 3), 120, dtype=np.uint8)),
        embedder=_FakeEmbedder(),
        quality_gate=_FakeQualityGate(passed=False, reason_codes=[ReasonCode.TOO_BLURRY]),
    )

    result = pipeline.process_frame(session, "frame")
    assert result["accepted"] is False
    assert session.accepted_frames == 0
    assert ReasonCode.TOO_BLURRY in result["reason_codes"]


def test_enrollment_template_requires_target_frames() -> None:
    session = EnrollmentSession(session_id="s3", target_frames=2)
    session.embeddings.append(np.ones(512, dtype=np.float32))
    pipeline = EnrollmentPipeline(
        detector=_FakeDetector([_face()], np.full((150, 150, 3), 120, dtype=np.uint8)),
        embedder=_FakeEmbedder(),
        quality_gate=_FakeQualityGate(passed=True),
    )

    with pytest.raises(ValueError) as exc:
        pipeline.build_template(session)
    assert ReasonCode.ENROLL_INCOMPLETE in str(exc.value)


def test_commit_template_replaces_existing_single_user_template() -> None:
    session = EnrollmentSession(session_id="s4", target_frames=2)
    session.embeddings = [
        np.ones(512, dtype=np.float32),
        np.ones(512, dtype=np.float32) * 0.5,
    ]
    repo = _FakeRepo()

    template_id, template = EnrollmentPipeline.commit_template(session, "default", repo)
    assert template_id == "template-1"
    assert repo.deleted is True
    assert repo.stored is not None
    assert repo.stored[0] == "default"
    assert template.shape[0] == 512

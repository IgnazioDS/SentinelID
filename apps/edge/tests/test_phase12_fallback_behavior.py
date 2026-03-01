"""v1.2 fallback hardening tests."""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from sentinelid_edge.core.config import settings
from sentinelid_edge.domain.reasons import ReasonCode
from sentinelid_edge.services.vision.detector import DetectedFace, FaceDetector, ModelUnavailableError
from sentinelid_edge.services.vision.embedder import FaceEmbedder


_FRAME_DATA = (
    "data:image/jpeg;base64,"
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wCEAAkGBxISEhUTEhIVFhUXFRUVFRUVFRUVFRUXFhUX"
    "FhUVFRUYHSggGBolHRUVITEhJSkrLi4uFx8zODMsNygtLisBCgoKDg0OGhAQGi0lHyUtLS0t"
    "LS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLf/AABEIAAEAAQMB"
    "IgACEQEDEQH/xAAXAAADAQAAAAAAAAAAAAAAAAAAAQID/8QAFhABAQEAAAAAAAAAAAAAAAAA"
    "AAER/8QAFgEBAQEAAAAAAAAAAAAAAAAAAgAB/8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAwD"
    "AQACEQMRAD8A0wD/AP/Z"
)


def _test_face() -> DetectedFace:
    return DetectedFace(
        bbox=(20.0, 20.0, 120.0, 120.0),
        landmarks=np.zeros((68, 2), dtype=np.float32),
        confidence=0.9,
        embedding=None,
    )


def test_detector_disallows_fallback_when_not_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    detector = FaceDetector(allow_fallback=False)
    monkeypatch.setattr(FaceDetector, "_get_insightface_model", classmethod(lambda cls: None))

    image = np.full((120, 120, 3), 127, dtype=np.uint8)
    faces, meta = detector.detect_faces_from_bgr(image)

    assert faces == []
    assert meta["model_unavailable"] is True
    assert meta["reason_codes"] == [ReasonCode.MODEL_UNAVAILABLE]


def test_detector_dev_requires_explicit_fallback_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "EDGE_ENV", "dev")
    monkeypatch.setattr(settings, "ALLOW_FALLBACK_EMBEDDINGS", False)
    detector = FaceDetector()
    monkeypatch.setattr(FaceDetector, "_get_insightface_model", classmethod(lambda cls: None))

    image = np.full((120, 120, 3), 127, dtype=np.uint8)
    faces, meta = detector.detect_faces_from_bgr(image)

    assert faces == []
    assert meta["reason_codes"] == [ReasonCode.MODEL_UNAVAILABLE]


def test_detector_dev_with_explicit_fallback_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    detector = FaceDetector(allow_fallback=True)
    monkeypatch.setattr(FaceDetector, "_get_insightface_model", classmethod(lambda cls: None))

    image = np.full((120, 120, 3), 127, dtype=np.uint8)
    faces, meta = detector.detect_faces_from_bgr(image)

    assert len(faces) == 1
    assert meta["fallback_used"] is True
    assert meta["reason_codes"] == [ReasonCode.FALLBACK_EMBEDDING_USED]


def test_embedder_raises_model_unavailable_when_fallback_disabled() -> None:
    detector = FaceDetector(allow_fallback=False)
    embedder = FaceEmbedder(detector=detector, allow_fallback=False)

    image = np.full((120, 120, 3), 127, dtype=np.uint8)
    with pytest.raises(ModelUnavailableError):
        embedder.extract_embedding(_FRAME_DATA, face=_test_face(), image_bgr=image)


def test_embedder_marks_fallback_usage_when_enabled() -> None:
    detector = FaceDetector(allow_fallback=True)
    embedder = FaceEmbedder(detector=detector, allow_fallback=True)

    image = np.full((120, 120, 3), 127, dtype=np.uint8)
    embedding = embedder.extract_embedding(_FRAME_DATA, face=_test_face(), image_bgr=image)

    assert embedding is not None
    assert embedding.shape[0] == 512
    assert embedder.last_fallback_used is True


def test_auth_frame_returns_503_when_model_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    import sentinelid_edge.main as main_mod
    from sentinelid_edge.main import app
    from sentinelid_edge.api.v1 import auth as auth_api

    async def _allow_token(_request):
        return "ok"

    monkeypatch.setattr(main_mod, "verify_bearer_token", _allow_token)
    image = np.full((120, 120, 3), 127, dtype=np.uint8)
    monkeypatch.setattr(auth_api._face_detector, "decode_frame_to_bgr", lambda _frame: image)
    monkeypatch.setattr(
        auth_api._face_detector,
        "detect_faces_from_bgr",
        lambda _image: ([], {"model_unavailable": True, "reason_codes": [ReasonCode.MODEL_UNAVAILABLE]}),
    )

    with TestClient(app) as client:
        headers = {"Authorization": "Bearer any-token"}
        start = client.post("/api/v1/auth/start", json={}, headers=headers)
        assert start.status_code == 200
        session_id = start.json()["session_id"]

        frame_resp = client.post(
            "/api/v1/auth/frame",
            json={"session_id": session_id, "frame": _FRAME_DATA},
            headers=headers,
        )

    assert frame_resp.status_code == 503
    assert frame_resp.json()["detail"]["reason_codes"] == [ReasonCode.MODEL_UNAVAILABLE.value]


def test_enroll_frame_returns_503_when_model_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    import sentinelid_edge.main as main_mod
    from sentinelid_edge.main import app
    from sentinelid_edge.api.v1 import enroll as enroll_api

    async def _allow_token(_request):
        return "ok"

    monkeypatch.setattr(main_mod, "verify_bearer_token", _allow_token)
    monkeypatch.setattr(
        enroll_api._pipeline,
        "process_frame",
        lambda _session, _frame: {
            "accepted": False,
            "reason_codes": [ReasonCode.MODEL_UNAVAILABLE],
            "quality": {},
            "accepted_frames": 0,
            "target_frames": 8,
        },
    )

    with TestClient(app) as client:
        headers = {"Authorization": "Bearer any-token"}
        start = client.post("/api/v1/enroll/start", json={}, headers=headers)
        assert start.status_code == 200
        session_id = start.json()["session_id"]

        frame_resp = client.post(
            "/api/v1/enroll/frame",
            json={"session_id": session_id, "frame": _FRAME_DATA},
            headers=headers,
        )

    assert frame_resp.status_code == 503
    assert frame_resp.json()["detail"]["reason_codes"] == [ReasonCode.MODEL_UNAVAILABLE.value]


def test_enrollment_pipeline_accepts_fallback_when_model_unavailable_but_fallback_active() -> None:
    from sentinelid_edge.services.enrollment.sessions import EnrollmentPipeline, EnrollmentSession
    from sentinelid_edge.services.vision.detector import DetectedFace

    class _Detector:
        def detect_faces(self, _frame_data: str):
            face = DetectedFace(
                bbox=(20.0, 20.0, 120.0, 120.0),
                landmarks=np.zeros((68, 2), dtype=np.float32),
                confidence=0.9,
                embedding=None,
            )
            return [face], {
                "model_unavailable": True,
                "fallback_used": True,
                "image_bgr": np.full((120, 120, 3), 127, dtype=np.uint8),
            }

    class _QualityGate:
        def evaluate(self, _image, _faces):
            class _Q:
                passed = True
                reason_codes = []
                metrics = {"num_faces": 1}

            return _Q()

    class _Embedder:
        last_fallback_used = True

        def extract_embedding(self, _frame_data: str, face=None, image_bgr=None):
            return np.ones((512,), dtype=np.float32)

    pipeline = EnrollmentPipeline(detector=_Detector(), embedder=_Embedder(), quality_gate=_QualityGate())
    session = EnrollmentSession(session_id="s1", target_frames=1)

    result = pipeline.process_frame(session, _FRAME_DATA)
    assert result["accepted"] is True
    assert result["accepted_frames"] == 1
    assert result["reason_codes"] == [ReasonCode.FALLBACK_EMBEDDING_USED]


def test_finish_auth_dev_fallback_relaxes_liveness_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    import sentinelid_edge.main as main_mod
    from sentinelid_edge.main import app
    from sentinelid_edge.api.v1 import auth as auth_api

    async def _allow_token(_request):
        return "ok"

    class _Template:
        embedding = np.ones((512,), dtype=np.float32)

    monkeypatch.setattr(main_mod, "verify_bearer_token", _allow_token)
    monkeypatch.setattr(auth_api.settings, "EDGE_ENV", "dev")
    monkeypatch.setattr(auth_api.settings, "ALLOW_FALLBACK_EMBEDDINGS", True)
    monkeypatch.setattr(auth_api._template_repo, "load_latest_template", lambda: _Template())

    with TestClient(app) as client:
        headers = {"Authorization": "Bearer any-token"}
        start = client.post("/api/v1/auth/start", json={}, headers=headers)
        assert start.status_code == 200
        session_id = start.json()["session_id"]

        session = auth_api._session_store.get_session(session_id)
        assert session is not None
        for challenge in session.challenges:
            challenge.completed = True
            challenge.passed = False
        session.liveness_passed = False
        session.latest_embedding = np.ones((512,), dtype=np.float32)
        session.latest_quality_reasons = [ReasonCode.FALLBACK_EMBEDDING_USED]
        session.risk_score = 0.471
        auth_api._session_store.save_session(session)

        finish = client.post(
            "/api/v1/auth/finish",
            json={"session_id": session_id},
            headers=headers,
        )

    assert finish.status_code == 200
    data = finish.json()
    assert data["decision"] == "allow"
    assert data["liveness_passed"] is True
    assert ReasonCode.FALLBACK_EMBEDDING_USED.value in data["reason_codes"]


def test_finish_auth_prod_keeps_liveness_denial_even_with_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    import sentinelid_edge.main as main_mod
    from sentinelid_edge.main import app
    from sentinelid_edge.api.v1 import auth as auth_api

    async def _allow_token(_request):
        return "ok"

    class _Template:
        embedding = np.ones((512,), dtype=np.float32)

    monkeypatch.setattr(main_mod, "verify_bearer_token", _allow_token)
    monkeypatch.setattr(auth_api.settings, "EDGE_ENV", "prod")
    monkeypatch.setattr(auth_api.settings, "ALLOW_FALLBACK_EMBEDDINGS", True)
    monkeypatch.setattr(auth_api._template_repo, "load_latest_template", lambda: _Template())

    with TestClient(app) as client:
        headers = {"Authorization": "Bearer any-token"}
        start = client.post("/api/v1/auth/start", json={}, headers=headers)
        assert start.status_code == 200
        session_id = start.json()["session_id"]

        session = auth_api._session_store.get_session(session_id)
        assert session is not None
        for challenge in session.challenges:
            challenge.completed = True
            challenge.passed = False
        session.liveness_passed = False
        session.latest_embedding = np.ones((512,), dtype=np.float32)
        session.latest_quality_reasons = [ReasonCode.FALLBACK_EMBEDDING_USED]
        session.risk_score = 0.471
        auth_api._session_store.save_session(session)

        finish = client.post(
            "/api/v1/auth/finish",
            json={"session_id": session_id},
            headers=headers,
        )

    assert finish.status_code == 200
    data = finish.json()
    assert data["decision"] == "deny"
    assert data["reason_codes"] == [ReasonCode.LIVENESS_FAILED.value, ReasonCode.FALLBACK_EMBEDDING_USED.value]

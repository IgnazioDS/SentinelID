from __future__ import annotations

import numpy as np
from fastapi.testclient import TestClient

from sentinelid_edge.domain.reasons import ReasonCode

_FRAME_DATA = (
    "data:image/jpeg;base64,"
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wCEAAkGBxISEhUTEhIVFhUXFRUVFRUVFRUVFRUXFhUX"
    "FhUVFRUYHSggGBolHRUVITEhJSkrLi4uFx8zODMsNygtLisBCgoKDg0OGhAQGi0lHyUtLS0t"
    "LS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLf/AABEIAAEAAQMB"
    "IgACEQEDEQH/xAAXAAADAQAAAAAAAAAAAAAAAAAAAQID/8QAFhABAQEAAAAAAAAAAAAAAAAA"
    "AAER/8QAFgEBAQEAAAAAAAAAAAAAAAAAAgAB/8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAwD"
    "AQACEQMRAD8A0wD/AP/Z"
)


def test_rate_dropped_frames_do_not_consume_session_frame_budget(monkeypatch) -> None:
    import sentinelid_edge.main as main_mod
    from sentinelid_edge.main import app
    from sentinelid_edge.api.v1 import auth as auth_api

    async def _allow_token(_request):
        return "ok"

    monkeypatch.setattr(main_mod, "verify_bearer_token", _allow_token)
    monkeypatch.setattr(auth_api.settings, "MAX_FRAMES_PER_SESSION", 1)
    monkeypatch.setattr(auth_api._frame_controller, "try_acquire", lambda _session_id: (False, "rate_capped"))

    with TestClient(app) as client:
        headers = {"Authorization": "Bearer any-token"}
        start = client.post("/api/v1/auth/start", json={}, headers=headers)
        assert start.status_code == 200
        session_id = start.json()["session_id"]

        first = client.post(
            "/api/v1/auth/frame",
            json={"session_id": session_id, "frame": _FRAME_DATA},
            headers=headers,
        )
        second = client.post(
            "/api/v1/auth/frame",
            json={"session_id": session_id, "frame": _FRAME_DATA},
            headers=headers,
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert "rate cap" in first.json()["detail"].lower()


def test_processed_frames_enforce_session_frame_budget(monkeypatch) -> None:
    import sentinelid_edge.main as main_mod
    from sentinelid_edge.main import app
    from sentinelid_edge.api.v1 import auth as auth_api

    async def _allow_token(_request):
        return "ok"

    monkeypatch.setattr(main_mod, "verify_bearer_token", _allow_token)
    monkeypatch.setattr(auth_api.settings, "MAX_FRAMES_PER_SESSION", 1)
    monkeypatch.setattr(auth_api._frame_controller, "try_acquire", lambda _session_id: (True, None))
    monkeypatch.setattr(
        auth_api._face_detector,
        "decode_frame_to_bgr",
        lambda _frame: np.full((32, 32, 3), 120, dtype=np.uint8),
    )
    monkeypatch.setattr(
        auth_api._face_detector,
        "detect_faces_from_bgr",
        lambda _image: ([], {"num_faces": 0, "reason_codes": [ReasonCode.NO_FACE]}),
    )

    with TestClient(app) as client:
        headers = {"Authorization": "Bearer any-token"}
        start = client.post("/api/v1/auth/start", json={}, headers=headers)
        assert start.status_code == 200
        session_id = start.json()["session_id"]

        first = client.post(
            "/api/v1/auth/frame",
            json={"session_id": session_id, "frame": _FRAME_DATA},
            headers=headers,
        )
        second = client.post(
            "/api/v1/auth/frame",
            json={"session_id": session_id, "frame": _FRAME_DATA},
            headers=headers,
        )

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["detail"] == "Frame limit exceeded for this session"

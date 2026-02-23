"""Phase 7 risk heuristic unit tests."""

import numpy as np

from sentinelid_edge.services.antifraud import heuristics


def _circular_landmarks(cx: float = 64.0, cy: float = 64.0) -> np.ndarray:
    angles = np.linspace(0, 2 * np.pi, 68, endpoint=False)
    xs = cx + 25.0 * np.cos(angles)
    ys = cy + 30.0 * np.sin(angles)
    return np.stack([xs, ys], axis=1).astype(np.float32)


def test_screen_moire_neutral_on_invalid_frame() -> None:
    score, reason = heuristics.screen_moire_score("not-a-real-frame")
    assert score == 0.0
    assert reason is None


def test_screen_moire_detects_annulus_pattern(monkeypatch) -> None:
    monkeypatch.setattr(
        heuristics,
        "_decode_frame_to_gray",
        lambda _frame: np.ones((64, 64), dtype=np.float32),
    )

    def fake_fft2(gray: np.ndarray) -> np.ndarray:
        h, w = gray.shape
        cy, cx = h // 2, w // 2
        ys, xs = np.ogrid[:h, :w]
        dist = np.sqrt((ys - cy) ** 2 + (xs - cx) ** 2)
        r_inner = min(h, w) // 8
        r_outer = min(h, w) // 3

        fft = np.ones((h, w), dtype=np.complex64)
        fft[(dist >= r_inner) & (dist <= r_outer)] = 1000.0 + 0.0j
        fft[dist > r_outer] = 1.0 + 0.0j
        return fft

    monkeypatch.setattr(heuristics.np.fft, "fft2", fake_fft2)
    monkeypatch.setattr(heuristics.np.fft, "fftshift", lambda arr: arr)

    score, reason = heuristics.screen_moire_score("synthetic")
    assert score > 0.9
    assert reason == "SPOOF_SUSPECT_SCREEN"


def test_boundary_blur_neutral_without_landmarks() -> None:
    score, reason = heuristics.boundary_blur_score("any", None)
    assert score == 0.0
    assert reason is None


def test_boundary_blur_detects_uniformity(monkeypatch) -> None:
    landmarks = _circular_landmarks()
    gray = np.zeros((128, 128), dtype=np.float32)

    xs = landmarks[:, 0]
    ys = landmarks[:, 1]
    face_cx = float(np.mean(xs))
    face_cy = float(np.mean(ys))
    face_radius = float(max(np.std(xs), np.std(ys), 10.0))

    ys_grid, xs_grid = np.ogrid[:128, :128]
    dist = np.sqrt((ys_grid - face_cy) ** 2 + (xs_grid - face_cx) ** 2)
    boundary_mask = (dist >= face_radius * 0.7) & (dist <= face_radius * 0.9)

    rng = np.random.default_rng(7)
    gray[boundary_mask] = rng.normal(100.0, 3.2, boundary_mask.sum()).astype(np.float32)

    monkeypatch.setattr(heuristics, "_decode_frame_to_gray", lambda _frame: gray)
    monkeypatch.setattr(heuristics, "_laplacian_variance", lambda _patch: 10.0)

    score, reason = heuristics.boundary_blur_score("synthetic", landmarks)
    assert score > 0.3
    assert reason == "SPOOF_SUSPECT_BOUNDARY"


def test_temporal_jitter_detects_static_replay() -> None:
    base = np.array([[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]], dtype=np.float32)
    history = [base.copy() for _ in range(6)]

    score, reason = heuristics.temporal_jitter_score(history)
    assert score >= 0.9
    assert reason == "SPOOF_SUSPECT_TEMPORAL"


def test_temporal_jitter_neutral_for_smooth_motion() -> None:
    base = np.array([[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]], dtype=np.float32)
    history = [base + (idx * 1.2) for idx in range(6)]

    score, reason = heuristics.temporal_jitter_score(history)
    assert score == 0.0
    assert reason is None

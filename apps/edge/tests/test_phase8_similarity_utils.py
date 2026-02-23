"""Phase 8 embedding and similarity utility tests."""

import numpy as np
import pytest

from sentinelid_edge.services.vision.embedder import (
    aggregate_embeddings,
    cosine_similarity,
    l2_normalize,
)


def test_l2_normalize_unit_norm() -> None:
    vec = np.array([3.0, 4.0], dtype=np.float32)
    out = l2_normalize(vec)
    assert np.isclose(np.linalg.norm(out), 1.0)


def test_aggregate_embeddings_mean_and_normalize() -> None:
    emb1 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    emb2 = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    template = aggregate_embeddings([emb1, emb2])
    assert template.shape == (3,)
    assert np.isclose(np.linalg.norm(template), 1.0)


def test_cosine_similarity_identical_vectors() -> None:
    a = np.array([0.2, 0.3, 0.4], dtype=np.float32)
    assert np.isclose(cosine_similarity(a, a), 1.0)


def test_cosine_similarity_mismatched_dimensions_raises() -> None:
    with pytest.raises(ValueError):
        cosine_similarity(np.array([1.0, 0.0]), np.array([1.0, 0.0, 0.0]))

"""NO_CONTEXT 임계값 판정 — 정책서 §5.4 (top-1 < τ → LOW_SIMILARITY)."""

import pytest

from src.domain.retrieval import RetrievedChunk
from src.retrieval.threshold import NoContextReason, judge


def chunk(similarity: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=str(similarity),
        content="x",
        permalink="",
        source_key="langchain_v1x",
        file_path="f",
        heading_path="h",
        token_count=10,
        site_url="",
        similarity=similarity,
    )


@pytest.mark.parametrize(
    ("top1", "passed"),
    [(0.31, True), (0.30, True), (0.2999, False)],  # 경계값 τ는 통과 (≥ τ)
)
def test_top1_against_tau(top1: float, passed: bool) -> None:
    decision = judge([chunk(top1), chunk(0.1)], tau=0.30)

    assert decision.passed is passed
    assert decision.top1_similarity == top1
    assert decision.reason == (None if passed else NoContextReason.LOW_SIMILARITY)


def test_no_results_is_low_similarity() -> None:
    decision = judge([], tau=0.30)

    assert not decision.passed
    assert decision.top1_similarity is None
    assert decision.reason == "LOW_SIMILARITY"


def test_uses_maximum_even_if_unsorted() -> None:
    assert judge([chunk(0.1), chunk(0.5)], tau=0.4).top1_similarity == 0.5

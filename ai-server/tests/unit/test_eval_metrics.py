"""검색 품질 지표 (evaluation.md §2.1·§2.2)."""

import pytest

from src.domain.retrieval import RetrievedChunk
from src.eval.metrics import (
    contamination_at_k,
    context_tokens,
    gold_flags,
    hit_at_k,
    max_score,
    mean,
    no_context_metrics,
    precision_at_k,
    rr_at_k,
)
from src.eval.questions import GoldSection


def _chunk(
    source_key: str, file_path: str, heading_path: str, similarity: float, tokens: int = 100
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=f"{file_path}#{heading_path}",
        content="",
        permalink="",
        source_key=source_key,
        file_path=file_path,
        heading_path=heading_path,
        token_count=tokens,
        similarity=similarity,
    )


V1 = "langchain_v1x"
V03 = "langchain_v03"
GOLD = [GoldSection(file_path="tools.mdx", heading_path="Tools > Create tools")]
CHUNKS = [
    _chunk(V03, "custom_tools.ipynb", "How to create tools", 0.82, 300),
    _chunk(V1, "tools.mdx", "Tools > Create tools > Basic tool definition", 0.80, 200),
    _chunk(V1, "agents.mdx", "Agents > Core components", 0.71, 150),
    _chunk(V1, "tools.mdx", "Tools > Create tools", 0.70, 120),
    _chunk(V03, "tool_calling.ipynb", "How to use chat models to call tools", 0.65, 90),
]


def test_gold_flags_use_file_and_section_match() -> None:
    assert gold_flags(CHUNKS, GOLD) == [False, True, False, True, False]


@pytest.mark.parametrize(("k", "hit", "rr"), [(1, 0, 0.0), (2, 1, 0.5), (5, 1, 0.5)])
def test_hit_and_reciprocal_rank(k: int, hit: int, rr: float) -> None:
    flags = gold_flags(CHUNKS, GOLD)

    assert hit_at_k(flags, k) == hit
    assert rr_at_k(flags, k) == rr


def test_precision_counts_gold_chunks_of_target_source_over_k() -> None:
    flags = gold_flags(CHUNKS, GOLD)

    assert precision_at_k(CHUNKS, flags, V1, 5) == pytest.approx(2 / 5)
    assert precision_at_k(CHUNKS, flags, V03, 5) == 0.0


def test_contamination_is_other_source_ratio_over_k() -> None:
    assert contamination_at_k(CHUNKS, V1, 5) == pytest.approx(2 / 5)
    assert contamination_at_k(CHUNKS, V1, 3) == pytest.approx(1 / 3)


def test_short_result_list_still_divides_by_k() -> None:
    chunks = CHUNKS[1:2]
    flags = gold_flags(chunks, GOLD)

    assert precision_at_k(chunks, flags, V1, 5) == pytest.approx(1 / 5)
    assert contamination_at_k(chunks, V1, 5) == 0.0


def test_context_tokens_and_max_score() -> None:
    assert context_tokens(CHUNKS, 3) == 650
    assert max_score(CHUNKS) == 0.82
    assert max_score([]) is None


def test_mean_ignores_missing_values() -> None:
    assert mean([1, None, 0]) == 0.5
    assert mean([None]) is None


def test_no_context_metrics() -> None:
    ret = [0.8, 0.7, 0.45, 0.6]  # 0.45 < τ → 오발동 1/4
    oos = [0.2, 0.3, 0.55]  # 2/3 NO_CONTEXT

    m = no_context_metrics(ret, oos, tau=0.5)

    assert m.recall == pytest.approx(2 / 3)
    assert m.fpr == pytest.approx(1 / 4)
    expected = 2 * (2 / 3) * (3 / 4) / ((2 / 3) + (3 / 4))
    assert m.f1 == pytest.approx(expected)


def test_no_context_metrics_requires_both_sets() -> None:
    with pytest.raises(ValueError):
        no_context_metrics([], [0.1], tau=0.5)

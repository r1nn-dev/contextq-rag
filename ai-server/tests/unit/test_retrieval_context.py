"""토큰 예산 기반 컨텍스트 조립 — 정책서 §5.3 (τ 이상만, 3,000토큰, 낮은 rank부터 제외)."""

import pytest

from src.domain.retrieval import RetrievedChunk
from src.ingest.metadata import count_tokens
from src.retrieval.context import chunk_tokens, select_context


def chunk(cid: str, similarity: float, tokens: int, content: str = "x") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=cid,
        content=content,
        permalink="",
        source_key="langchain_v1x",
        file_path="f",
        heading_path="h",
        token_count=tokens,
        site_url="",
        similarity=similarity,
    )


def ids(chunks: list[RetrievedChunk]) -> list[str]:
    return [c["chunk_id"] for c in chunks]


def test_keeps_only_chunks_at_or_above_tau_in_rank_order() -> None:
    chunks = [chunk("b", 0.5, 10), chunk("a", 0.8, 10), chunk("c", 0.30, 10), chunk("d", 0.29, 10)]

    selection = select_context(chunks, tau=0.30, budget_tokens=3000)

    assert ids(selection.chunks) == ["a", "b", "c"]
    assert (selection.total_tokens, selection.below_tau, selection.over_budget) == (30, 1, 0)


def test_drops_lowest_ranks_first_without_splitting() -> None:
    chunks = [
        chunk("a", 0.9, 1200),
        chunk("b", 0.8, 1200),
        chunk("c", 0.7, 700),
        chunk("d", 0.6, 100),
    ]

    selection = select_context(chunks, tau=0.3, budget_tokens=3000)

    # a+b = 2400, c를 더하면 3100 > 3000 → c와 그보다 낮은 d를 뺀다 (d가 들어갈 자리가 있어도)
    assert ids(selection.chunks) == ["a", "b"]
    assert (selection.total_tokens, selection.over_budget) == (2400, 2)


def test_budget_exactly_reached_is_kept() -> None:
    selection = select_context([chunk("a", 0.9, 1500), chunk("b", 0.8, 1500)], 0.3, 3000)

    assert ids(selection.chunks) == ["a", "b"]


def test_keeps_top1_even_if_it_alone_exceeds_budget(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("WARNING", logger="src.retrieval.context"):
        selection = select_context([chunk("a", 0.9, 3500), chunk("b", 0.8, 10)], 0.3, 3000)

    assert ids(selection.chunks) == ["a"]
    assert [r.getMessage() for r in caplog.records] == ["context_top1_over_budget"]


def test_nothing_above_tau_gives_empty_context() -> None:
    selection = select_context([chunk("a", 0.2, 10)], tau=0.3, budget_tokens=3000)

    assert selection.chunks == [] and selection.below_tau == 1


def test_missing_token_count_is_counted_with_tiktoken() -> None:
    text = "LangChain agents call tools."

    assert chunk_tokens(chunk("a", 0.9, 0, text)) == count_tokens(text) > 0
    assert chunk_tokens(chunk("a", 0.9, 42, text)) == 42

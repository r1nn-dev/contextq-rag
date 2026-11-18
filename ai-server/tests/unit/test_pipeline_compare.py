"""비교 모드 오케스트레이션 — 측별 τ 판정·출처 번호·후처리·오류 종결 (정책서 §5.6, 부록 B.2·B.4)."""

import asyncio
from collections.abc import Sequence
from datetime import date
from typing import Any

from src.config.rag_config import load_rag_config
from src.domain.chat_stream import HistoryMessage
from src.domain.compare import CompareChange, CompareResult, CompareSide
from src.domain.retrieval import RetrievedChunk
from src.ingest.embedder import EmbeddingError
from src.pipeline.compare import ComparePipeline, CompareRequest
from src.pipeline.compare_generator import CompareGeneration, CompareParseError
from src.pipeline.generator import LLMCallError
from src.pipeline.rewriter import RewriteResult, RewriteStatus
from src.pipeline.single import StreamProgress
from src.retrieval.errors import IndexNotActiveError
from src.retrieval.pointers import ActiveIndex
from src.retrieval.search import RetrievalResult
from tests.contract.sse_contract import validate_stream
from tests.unit.test_pipeline_rewriter import FixedRewriter
from tests.unit.test_pipeline_single import chunk

SHA_A, SHA_B = "a" * 40, "b" * 40
INDEX_A = ActiveIndex("langchain_v03", "v0.3", 6, SHA_A, date(2026, 11, 18), 900,
                      "text-embedding-3-small", "LangChain v0.3")  # fmt: skip
INDEX_B = ActiveIndex("langchain_v1x", "v1.x", 10, SHA_B, date(2026, 11, 18), 700,
                      "text-embedding-3-small", "LangChain v1.x")  # fmt: skip
PASS, FAIL = 0.9, 0.1  # τ: v0.3 0.29 · v1.x 0.34


class SideSearcher:
    """source_key별 결과. 측마다 임베딩·검색 시간이 다르게 나온다."""

    def __init__(
        self, a: list[RetrievedChunk], b: list[RetrievedChunk], error: Exception | None = None
    ):
        self.results = {"langchain_v03": (a, 70), "langchain_v1x": (b, 90)}
        self.error = error
        self.calls: list[tuple[str, str, int]] = []

    def search(
        self, query: str, source_key: str, top_k: int = 5, *, index: ActiveIndex | None = None
    ) -> RetrievalResult:
        self.calls.append((query, source_key, top_k))
        if self.error:
            raise self.error
        assert index is not None and index.source_key == source_key
        chunks, ms = self.results[source_key]
        return RetrievalResult(index, chunks, embed_ms=ms, retrieve_ms=ms + 10)


def side_result(**overrides: Any) -> CompareResult:
    base = {
        "version_a": CompareSide(summary="v0.3 설명 [A1]", citations=["A1"], no_evidence=False),
        "version_b": CompareSide(summary="v1.x 설명 [B2]", citations=["B2"], no_evidence=False),
        "changes": [
            CompareChange(aspect="함수", a="old", b="new", citations_a=["A1"], citations_b=["B1"])
        ],
    }
    return CompareResult(**{**base, **overrides})


class FakeCompareGenerator:
    def __init__(self, outcome: CompareResult | Exception) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, Any]] = []

    async def generate_compare(
        self,
        query: str,
        chunks_a: Sequence[RetrievedChunk],
        chunks_b: Sequence[RetrievedChunk],
        *,
        display_name_a: str,
        display_name_b: str,
        prompt_version: str,
    ) -> CompareGeneration:
        self.calls.append({"query": query, "a": list(chunks_a), "b": list(chunks_b),
                           "names": (display_name_a, display_name_b)})  # fmt: skip
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return CompareGeneration(self.outcome, "gpt-4o-mini-2024-07-18",
                                 {"prompt": 2000, "completion": 500}, 1)  # fmt: skip


def run(
    searcher: SideSearcher,
    generator: FakeCompareGenerator,
    *,
    rewriter: Any = None,
    history: tuple[HistoryMessage, ...] = (),
) -> list[dict[str, Any]]:
    ticks = iter(float(i) for i in range(1, 100))
    pipeline = ComparePipeline(
        searcher, generator, load_rag_config().retrieval, rewriter=rewriter,
        clock=lambda: next(ticks),
    )  # fmt: skip
    req = CompareRequest(
        "req-c", "에이전트 생성 방식 차이는?", INDEX_A, INDEX_B, "compare_v1", history
    )

    async def collect() -> list[dict[str, Any]]:
        return [e async for e in pipeline.run(req, StreamProgress(started=0.0))]

    events = asyncio.run(collect())
    validate_stream(events, leg="upstream")
    return events


def test_both_sides_with_evidence_complete_with_compare_result() -> None:
    searcher = SideSearcher([chunk(1, PASS), chunk(2, PASS)], [chunk(3, PASS), chunk(4, PASS)])
    generator = FakeCompareGenerator(side_result())

    meta, done = run(searcher, generator)

    assert [s["rank"] for s in meta["sources"]] == ["A1", "A2", "B1", "B2"]
    assert (meta["sourceKeyA"], meta["sourceKeyB"]) == ("langchain_v03", "langchain_v1x")
    assert (meta["ingestRunIdA"], meta["commitShaB"]) == (6, SHA_B)
    assert "sourceKey" not in meta and meta["noContext"] is False
    assert done["status"] == "COMPLETED" and done["finishReason"] == "stop"
    assert done["compareResult"]["changes"][0]["citations_b"] == ["B1"]
    assert done["usage"] == {"prompt": 2000, "completion": 500}
    assert done["promptVersion"] == "compare_v1"
    assert done["latency"]["ttftMs"] is None
    assert (done["latency"]["embedMs"], done["latency"]["retrieveMs"]) == (
        90,
        100,
    )  # 두 측 중 큰 값
    assert generator.calls[0]["names"] == ("LangChain v0.3", "LangChain v1.x")


def test_one_side_without_evidence_is_fixed_and_has_no_changes() -> None:
    searcher = SideSearcher([chunk(1, FAIL)], [chunk(3, PASS)])
    generator = FakeCompareGenerator(side_result(version_b=CompareSide(
        summary="v1.x 설명 [B1]", citations=["B1"], no_evidence=False)))  # fmt: skip

    meta, done = run(searcher, generator)

    assert [s["rank"] for s in meta["sources"]] == ["B1"]  # 근거 없는 측 출처는 넣지 않는다
    assert generator.calls[0]["a"] == []
    result = done["compareResult"]
    assert result["version_a"] == {"summary": "", "citations": [], "no_evidence": True}
    assert result["version_b"]["citations"] == ["B1"]
    assert result["changes"] == []
    assert done["status"] == "COMPLETED"


def test_both_sides_without_evidence_skip_generation() -> None:
    generator = FakeCompareGenerator(side_result())

    meta, done = run(SideSearcher([chunk(1, FAIL)], []), generator)

    assert meta["noContext"] is True and meta["sources"] == []
    assert (done["status"], done["statusReason"]) == ("NO_CONTEXT", "LOW_SIMILARITY")
    assert "compareResult" not in done and done["usage"] is None
    assert generator.calls == []  # INV-07


def test_invalid_citations_are_removed_and_reported() -> None:
    searcher = SideSearcher([chunk(1, PASS)], [chunk(3, PASS)])
    raw = side_result(
        version_a=CompareSide(summary="설명 [A1][A4]", citations=["A1", "A4"], no_evidence=False),
        version_b=CompareSide(summary="설명 [B1]", citations=["B1", "A1"], no_evidence=False),
    )

    _, done = run(searcher, FakeCompareGenerator(raw))

    assert done["compareResult"]["version_a"] == {
        "summary": "설명 [A1]", "citations": ["A1"], "no_evidence": False}  # fmt: skip
    assert done["invalidCitations"] == ["A1", "A4"]  # B측의 A1(반대 측) + 범위 밖 A4


def test_parse_failure_ends_with_compare_parse_error_after_meta() -> None:
    searcher = SideSearcher([chunk(1, PASS)], [chunk(3, PASS)])

    meta, error = run(searcher, FakeCompareGenerator(CompareParseError("x")))

    assert meta["event"] == "meta"
    assert (error["event"], error["code"], error["partial"]) == (
        "error",
        "COMPARE_PARSE_ERROR",
        False,
    )


def test_llm_failure_ends_with_llm_error() -> None:
    searcher = SideSearcher([chunk(1, PASS)], [chunk(3, PASS)])

    _, error = run(searcher, FakeCompareGenerator(LLMCallError("down")))

    assert error["code"] == "LLM_ERROR"


def test_search_errors_end_before_meta() -> None:
    generator = FakeCompareGenerator(side_result())

    [embedding] = run(SideSearcher([], [], error=EmbeddingError("x")), generator)
    [index] = run(SideSearcher([], [], error=IndexNotActiveError("gone")), generator)

    assert embedding["code"] == "LLM_ERROR" and index["code"] == "INDEX_NOT_ACTIVE"
    assert generator.calls == []


def test_rewritten_query_searches_both_sides_and_original_question_generates() -> None:
    searcher = SideSearcher([chunk(1, PASS)], [chunk(3, PASS)])
    generator = FakeCompareGenerator(side_result(changes=[]))
    rewriter = FixedRewriter(RewriteResult("AgentExecutor 생성", "AgentExecutor 생성",
                                           RewriteStatus.OK, 300))  # fmt: skip
    history = (HistoryMessage(role="user", content="AgentExecutor는?"),)

    meta, done = run(searcher, generator, rewriter=rewriter, history=history)

    rewritten = "AgentExecutor 생성"
    assert {(q, k) for q, k, _ in searcher.calls} == {
        (rewritten, "langchain_v03"), (rewritten, "langchain_v1x")}  # fmt: skip
    assert all(top_k == 8 for _, _, top_k in searcher.calls)
    assert generator.calls[0]["query"] == "에이전트 생성 방식 차이는?"
    assert meta["rewrittenQuery"] == "AgentExecutor 생성"
    assert done["latency"]["rewriteMs"] == 300

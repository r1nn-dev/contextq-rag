"""단일 모드 오케스트레이션 — 모든 경로의 SSE 계약(upstream), INV-07·08 (api-spec 부록 B.1)."""

from collections.abc import AsyncIterator, Sequence
from datetime import date
from typing import Any

import pytest

from src.config.rag_config import load_rag_config
from src.domain.retrieval import RetrievedChunk
from src.ingest.embedder import EmbeddingError
from src.pipeline.generator import LLMCallError
from src.pipeline.single import SingleModePipeline, SingleRequest, StreamProgress
from src.retrieval.errors import IndexNotActiveError
from src.retrieval.pointers import ActiveIndex
from src.retrieval.search import RetrievalResult
from tests.contract.sse_contract import validate_stream

SHA = "c" * 40
INDEX = ActiveIndex("langchain_v1x", "v1.x", 3, SHA, date(2026, 11, 17), 120,
                    "text-embedding-3-small", "LangChain v1.x")  # fmt: skip


def chunk(i: int, similarity: float, tokens: int = 100) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=f"c{i}",
        content=f"content {i}",
        permalink=f"https://github.com/langchain-ai/docs/blob/{SHA}/src/{i}.mdx?plain=1#L1-L9",
        source_key="langchain_v1x",
        file_path=f"src/{i}.mdx",
        heading_path=f"Doc > S{i}",
        token_count=tokens,
        site_url=f"https://docs.langchain.com/oss/python/{i}",
        similarity=similarity,
    )


class FakeSearcher:
    def __init__(self, chunks: list[RetrievedChunk] | None = None, error: Exception | None = None):
        self.chunks = chunks or []
        self.error = error
        self.calls: list[tuple[str, str, int, ActiveIndex | None]] = []

    def search(
        self, query: str, source_key: str, top_k: int = 5, *, index: ActiveIndex | None = None
    ) -> RetrievalResult:
        self.calls.append((query, source_key, top_k, index))
        if self.error:
            raise self.error
        assert index is not None
        return RetrievalResult(index, self.chunks, embed_ms=80, retrieve_ms=120)


class FakeStream:
    def __init__(self, tokens: Sequence[str], finish: str = "stop", fail_after: int | None = None,
                 crash: bool = False) -> None:  # fmt: skip
        self.tokens = list(tokens)
        self.finish = finish
        self.fail_after = fail_after
        self.crash = crash
        self.model: str | None = None
        self.finish_reason: str | None = None
        self.usage: Any = None
        self.closed = False

    async def _gen(self) -> AsyncIterator[str]:
        for i, token in enumerate(self.tokens):
            if self.fail_after is not None and i == self.fail_after:
                raise LLMCallError("boom")
            if self.crash:
                raise RuntimeError("unexpected")
            self.model = "gpt-4o-mini-2024-07-18"
            yield token
        self.finish_reason = self.finish
        self.usage = {"prompt": 900, "completion": len(self.tokens)}

    def __aiter__(self) -> AsyncIterator[str]:
        return self._gen()

    async def aclose(self) -> None:
        self.closed = True


class FakeGenerator:
    def __init__(self, stream: FakeStream) -> None:
        self.stream = stream
        self.calls: list[dict[str, Any]] = []

    def generate_stream(self, query: str, chunks: Sequence[RetrievedChunk], *, display_name: str,
                        prompt_version: str) -> FakeStream:  # fmt: skip
        self.calls.append(
            {"query": query, "chunks": list(chunks), "display_name": display_name,
             "prompt_version": prompt_version}
        )  # fmt: skip
        return self.stream


REQUEST = SingleRequest("req-1", "에이전트는 어떻게 만드나요?", INDEX, "single_v1")


async def run(searcher: FakeSearcher, generator: FakeGenerator) -> list[dict[str, Any]]:
    ticks = iter(float(i) for i in range(1, 100))
    pipeline = SingleModePipeline(
        searcher, generator, load_rag_config().retrieval, clock=lambda: next(ticks)
    )
    progress = StreamProgress(started=0.0)
    events = [e async for e in pipeline.run(REQUEST, progress)]
    validate_stream(events, leg="upstream")
    return events


async def test_completed_answer_streams_meta_tokens_done() -> None:
    searcher = FakeSearcher([chunk(1, 0.82), chunk(2, 0.61), chunk(3, 0.2)])
    stream = FakeStream(["LangChain v1.x 기준", "입니다 [1][2]. ", "없는 번호 [5]"])
    generator = FakeGenerator(stream)

    meta, *tokens, done = await run(searcher, generator)

    assert searcher.calls == [(REQUEST.question, "langchain_v1x", 8, INDEX)]  # rag.yaml top_k
    assert meta["noContext"] is False and meta["ingestRunId"] == 3
    assert (meta["commitSha"], meta["ingestedAt"]) == (SHA, "2026-11-17")
    assert [s["rank"] for s in meta["sources"]] == [1, 2]  # τ 미만(0.2) 제외
    assert [c["chunk_id"] for c in generator.calls[0]["chunks"]] == ["c1", "c2"]
    assert generator.calls[0]["display_name"] == "LangChain v1.x"
    assert "".join(t["t"] for t in tokens) == "LangChain v1.x 기준입니다 [1][2]. 없는 번호 [5]"
    assert done["status"] == "COMPLETED" and done["finishReason"] == "stop"
    assert done["invalidCitations"] == [5]  # INV-08
    assert done["usage"] == {"prompt": 900, "completion": 3}
    assert (done["model"], done["promptVersion"]) == ("gpt-4o-mini-2024-07-18", "single_v1")
    latency = done["latency"]
    assert latency["rewriteMs"] is None
    assert (latency["embedMs"], latency["retrieveMs"]) == (80, 120)
    assert latency["ttftMs"] is not None and latency["totalMs"] >= latency["ttftMs"]
    assert stream.closed


@pytest.mark.parametrize("chunks", [[chunk(1, 0.29)], []])
async def test_low_similarity_never_calls_the_generator(chunks: list[RetrievedChunk]) -> None:
    generator = FakeGenerator(FakeStream(["x"]))

    meta, done = await run(FakeSearcher(chunks), generator)

    assert generator.calls == []  # INV-07: 생성 LLM 호출 0회
    assert meta["noContext"] is True and meta["sources"] == []
    assert (done["status"], done["statusReason"]) == ("NO_CONTEXT", "LOW_SIMILARITY")
    assert done["usage"] is None and done["model"] is None
    assert done["latency"]["ttftMs"] is None


async def test_sentinel_ends_as_llm_abstain_without_tokens() -> None:
    stream = FakeStream(["[[NO_", "ANSWER]]", " 근거 없음"])

    meta, done = await run(FakeSearcher([chunk(1, 0.9)]), FakeGenerator(stream))

    assert meta["noContext"] is False and len(meta["sources"]) == 1
    assert (done["status"], done["statusReason"]) == ("NO_CONTEXT", "LLM_ABSTAIN")
    assert stream.closed


async def test_sentinel_after_version_header_is_llm_abstain() -> None:
    """#108: 'LangChain v1.x 기준 [[NO_ANSWER]]'도 토큰 없이 NO_CONTEXT로 끝난다."""
    stream = FakeStream(["LangChain v1.x 기준", "\n\n", "[[NO_ANSWER]]"])

    meta, done = await run(FakeSearcher([chunk(1, 0.9)]), FakeGenerator(stream))

    assert meta["event"] == "meta"
    assert (done["status"], done["statusReason"]) == ("NO_CONTEXT", "LLM_ABSTAIN")


async def test_length_finish_is_partial() -> None:
    stream = FakeStream(["잘린 답변"], finish="length")

    *_, done = await run(FakeSearcher([chunk(1, 0.9)]), FakeGenerator(stream))

    assert (done["status"], done["statusReason"]) == ("PARTIAL", "LENGTH")


async def test_embedding_failure_before_meta_is_a_lone_error() -> None:
    [error] = await run(FakeSearcher(error=EmbeddingError("x")), FakeGenerator(FakeStream([])))

    assert (error["code"], error["partial"]) == ("LLM_ERROR", False)


async def test_index_error_mid_request_keeps_its_code() -> None:
    [error] = await run(
        FakeSearcher(error=IndexNotActiveError("gone")), FakeGenerator(FakeStream([]))
    )

    assert error["code"] == "INDEX_NOT_ACTIVE"


@pytest.mark.parametrize(("fail_after", "partial"), [(0, False), (1, True)])
async def test_llm_failure_after_meta_is_error_with_partial_flag(
    fail_after: int, partial: bool
) -> None:
    stream = FakeStream(["첫 토큰 ", "둘째"], fail_after=fail_after)

    events = await run(FakeSearcher([chunk(1, 0.9)]), FakeGenerator(stream))

    assert events[-1]["code"] == "LLM_ERROR"
    assert events[-1]["partial"] is partial
    assert stream.closed


async def test_unexpected_exception_still_ends_with_one_terminal_event() -> None:
    events = await run(FakeSearcher([chunk(1, 0.9)]), FakeGenerator(FakeStream(["a"], crash=True)))

    assert events[-1]["code"] == "INTERNAL_ERROR"


async def test_closing_the_event_stream_closes_the_llm_stream() -> None:
    stream = FakeStream(["a ", "b ", "c "])
    pipeline = SingleModePipeline(
        FakeSearcher([chunk(1, 0.9)]), FakeGenerator(stream), load_rag_config().retrieval
    )
    events = pipeline.run(REQUEST, StreamProgress(started=0.0))

    assert (await events.__anext__())["event"] == "meta"
    assert (await events.__anext__())["event"] == "token"
    await events.aclose()  # 클라이언트 연결 끊김

    assert stream.closed

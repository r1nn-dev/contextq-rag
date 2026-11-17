"""단일 모드 검색 → 판정 → 생성 오케스트레이션 — api-spec.md §6.1 처리 파이프라인, 부록 B.1.

이벤트 순서는 `meta → token* → (done | error)`이고 meta 전 오류는 `error` 하나로 끝난다(INV-06).
- LOW_SIMILARITY(top-1 < τ)면 생성기를 부르지 않는다(INV-07).
- sentinel을 감지하면 토큰 없이 NO_CONTEXT(LLM_ABSTAIN)로 끝내고 생성 스트림을 닫는다.
- 이 단계의 오류는 HTTP 상태가 아니라 `error` 이벤트다(INV-09). 하트비트·최대 시간은 라우터.
"""

import asyncio
import hashlib
import logging
import time
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

from src.config.rag_config import RetrievalConfig
from src.domain.chat_stream import (
    DoneEvent,
    Latency,
    MetaEvent,
    error_event,
    source_payload,
    token_event,
)
from src.domain.retrieval import RetrievedChunk
from src.ingest.embedder import EmbeddingError
from src.pipeline.citations import invalid_citations
from src.pipeline.generator import LLMCallError
from src.pipeline.prompts import version_header
from src.pipeline.sentinel import SentinelGate
from src.retrieval.context import select_context
from src.retrieval.errors import RetrievalError
from src.retrieval.pointers import ActiveIndex
from src.retrieval.search import RetrievalResult
from src.retrieval.threshold import NoContextReason, judge

logger = logging.getLogger(__name__)

LLM_ERROR_MESSAGE = "답변을 생성하는 중 오류가 발생했습니다. 다시 질문해 주세요."
INTERNAL_ERROR_MESSAGE = "요청을 처리하는 중 서버 오류가 발생했습니다."


class Searcher(Protocol):
    def search(
        self, query: str, source_key: str, top_k: int = 5, *, index: ActiveIndex | None = None
    ) -> RetrievalResult: ...


class TokenStream(Protocol):
    model: str | None
    finish_reason: str | None
    usage: Any

    def __aiter__(self) -> AsyncIterator[str]: ...

    async def aclose(self) -> None: ...


class Generator(Protocol):
    def generate_stream(
        self,
        query: str,
        chunks: Sequence[RetrievedChunk],
        *,
        display_name: str,
        prompt_version: str,
    ) -> TokenStream: ...


@dataclass(frozen=True)
class SingleRequest:
    request_id: str
    question: str
    index: ActiveIndex  # 요청 시작 시 확정한 run (R-4-1)
    prompt_version: str

    @property
    def source_key(self) -> str:
        return self.index.source_key


@dataclass
class StreamProgress:
    """라우터와 공유하는 진행 상태 — 최대 시간 종결(MAX_DURATION) 때 done을 만든다."""

    started: float
    tokens: int = 0
    answer: list[str] = field(default_factory=list)
    latency: Latency = field(default_factory=Latency)
    model: str | None = None

    def elapsed_ms(self, now: float) -> int:
        return max(0, round((now - self.started) * 1000))


def question_digest(question: str) -> dict[str, Any]:
    """정책서 §9.4 — 질문 원문 대신 길이·해시만 로그에 남긴다."""
    return {
        "question_len": len(question),
        "question_sha256": hashlib.sha256(question.encode("utf-8")).hexdigest()[:16],
    }


def _status_of(finish_reason: str | None) -> tuple[str, str | None]:
    """정책서 §10.2 — stop → COMPLETED, length → PARTIAL(LENGTH), 그 밖 → PARTIAL(사유)."""
    if finish_reason in (None, "stop"):
        return "COMPLETED", None
    return "PARTIAL", finish_reason.upper()


class SingleModePipeline:
    def __init__(
        self,
        retriever: Searcher,
        generator: Generator,
        retrieval: RetrievalConfig,
        *,
        tau_overrides: Mapping[str, float] | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.retriever = retriever
        self.generator = generator
        self.retrieval = retrieval
        self.tau_overrides = dict(tau_overrides or {})
        self.clock = clock

    async def run(
        self, req: SingleRequest, progress: StreamProgress
    ) -> AsyncGenerator[dict[str, Any]]:
        inner = self._run(req, progress)
        try:
            async for event in inner:
                yield event
        except Exception:  # 종결 이벤트 1회 보장 (INV-06)
            logger.exception("stream_internal_error", extra={"request_id": req.request_id})
            yield error_event(
                "INTERNAL_ERROR",
                INTERNAL_ERROR_MESSAGE,
                req.request_id,
                partial=progress.tokens > 0,
            )
        finally:
            # 바깥이 닫히면(클라이언트 취소) 안쪽 생성기도 바로 닫아 생성 스트림을 close한다
            await inner.aclose()

    async def _run(
        self, req: SingleRequest, progress: StreamProgress
    ) -> AsyncGenerator[dict[str, Any]]:
        top_k = self.retrieval.top_k
        try:
            result = await asyncio.to_thread(
                self.retriever.search, req.question, req.source_key, top_k, index=req.index
            )
        except EmbeddingError:
            logger.error("embedding_failed", extra={"request_id": req.request_id}, exc_info=True)
            yield error_event("LLM_ERROR", LLM_ERROR_MESSAGE, req.request_id, partial=False)
            return
        except RetrievalError as exc:
            yield error_event(exc.code, str(exc), req.request_id, partial=False)
            return
        progress.latency.embed_ms = result.embed_ms
        progress.latency.retrieve_ms = result.retrieve_ms

        tau = self.retrieval.tau(req.source_key, self.tau_overrides)
        decision = judge(result.chunks, tau)
        logger.info(
            "retrieval_done",
            extra={
                "request_id": req.request_id,
                "ingest_run_id": req.index.run_id,
                "max_similarity": decision.top1_similarity,
                "chunks_count": len(result.chunks),
                "discarded": result.discarded,
                "latency_ms": result.embed_ms + result.retrieve_ms,
            },
        )
        meta = MetaEvent(
            request_id=req.request_id,
            source_key=req.source_key,
            ingest_run_id=req.index.run_id,
            commit_sha=req.index.commit_sha,
            ingested_at=req.index.ingested_at,
            no_context=not decision.passed,
        )
        if not decision.passed:  # INV-07: 생성기를 부르지 않는다
            logger.info(
                "no_context_triggered",
                extra={
                    "request_id": req.request_id,
                    "max_similarity": decision.top1_similarity,
                    "tau": tau,
                },
            )
            yield meta.to_dict()
            yield self._done(
                req, progress, "NO_CONTEXT", NoContextReason.LOW_SIMILARITY, model=None
            ).to_dict()
            return

        selection = select_context(result.chunks, tau, self.retrieval.context_budget_tokens)
        sources = [source_payload(rank, c) for rank, c in enumerate(selection.chunks, start=1)]
        yield replace(meta, sources=sources).to_dict()

        display_name = req.index.display_name or req.source_key
        stream = self.generator.generate_stream(
            req.question,
            selection.chunks,
            display_name=display_name,
            prompt_version=req.prompt_version,
        )
        logger.info(
            "llm_stream_start",
            extra={"request_id": req.request_id, "context_tokens": selection.total_tokens},
        )
        gate = SentinelGate(header=version_header(display_name))
        try:
            try:
                async for text in stream:
                    progress.model = stream.model
                    released = gate.feed(text)
                    if gate.abstained:
                        break  # 남은 생성은 받지 않는다 (finally에서 스트림 close)
                    if released:
                        yield self._token(released, progress)
                if not gate.abstained:
                    released = gate.flush()
                    if released:
                        yield self._token(released, progress)
            finally:
                await stream.aclose()
        except LLMCallError:
            logger.error("llm_stream_failed", extra={"request_id": req.request_id}, exc_info=True)
            yield error_event(
                "LLM_ERROR", LLM_ERROR_MESSAGE, req.request_id, partial=progress.tokens > 0
            )
            return

        progress.model = stream.model
        logger.info(
            "llm_stream_done",
            extra={
                "request_id": req.request_id,
                "completion_tokens": (stream.usage or {}).get("completion"),
                "ttft_ms": progress.latency.ttft_ms,
                "abstained": gate.abstained,
            },
        )
        if gate.abstained:
            yield self._done(
                req, progress, "NO_CONTEXT", NoContextReason.LLM_ABSTAIN, model=stream.model
            ).to_dict()
            return
        status, reason = _status_of(stream.finish_reason)
        yield self._done(
            req,
            progress,
            status,
            reason,
            model=stream.model,
            finish_reason=stream.finish_reason,
            usage=stream.usage,
            invalid=invalid_citations("".join(progress.answer), len(sources)),
        ).to_dict()

    def _token(self, text: str, progress: StreamProgress) -> dict[str, Any]:
        if progress.tokens == 0:
            progress.latency.ttft_ms = progress.elapsed_ms(self.clock())
        progress.tokens += 1
        progress.answer.append(text)
        return token_event(text)

    def _done(
        self,
        req: SingleRequest,
        progress: StreamProgress,
        status: Any,
        reason: str | None,
        *,
        model: str | None,
        finish_reason: str | None = None,
        usage: Any = None,
        invalid: list[int] | None = None,
    ) -> DoneEvent:
        progress.latency.total_ms = progress.elapsed_ms(self.clock())
        return DoneEvent(
            status=status,
            latency=progress.latency,
            status_reason=str(reason) if reason else None,
            finish_reason=finish_reason,
            usage=dict(usage) if usage else None,
            invalid_citations=invalid or [],
            model=model,
            prompt_version=req.prompt_version,
        )

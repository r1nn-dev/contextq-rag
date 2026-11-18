"""비교 모드 검색 → 판정 → 생성 → 후처리 — ADR-010, 정책서 §5.6, rag-pipeline.md §5.

이벤트는 `meta → (done | error)`이고 token은 없다(부록 B.2). meta 전 오류는 `error` 하나로 끝난다.
- 재작성 질의 하나로 A·B를 병렬 검색하고(검색마다 질의 임베딩 1회), 측별 τ로 따로 판정한다.
- 양쪽 미달이면 생성기를 부르지 않는다(INV-07).
- 한쪽 미달이면 그 측 출처를 빼고 근거 없음으로 고정한다.
- 생성 결과는 `check_compare`로 후처리한 뒤 `done.compareResult`로 보낸다.
- 30초 상한·하트비트는 라우터(`sse.pump`)가 맡는다.
"""

import asyncio
import logging
import time
from collections.abc import AsyncGenerator, Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Protocol

from src.config.rag_config import RetrievalConfig
from src.domain.chat_stream import (
    CompareMetaEvent,
    DoneEvent,
    HistoryMessage,
    error_event,
    source_payload,
)
from src.domain.retrieval import RetrievedChunk
from src.ingest.embedder import EmbeddingError
from src.pipeline.compare_checks import check_compare
from src.pipeline.compare_generator import CompareGeneration, CompareParseError
from src.pipeline.generator import LLMCallError
from src.pipeline.rewriter import QueryRewriter, SkippingRewriter
from src.pipeline.single import (
    INTERNAL_ERROR_MESSAGE,
    LLM_ERROR_MESSAGE,
    Searcher,
    StreamProgress,
)
from src.retrieval.context import select_context
from src.retrieval.errors import RetrievalError
from src.retrieval.pointers import ActiveIndex
from src.retrieval.search import RetrievalResult
from src.retrieval.threshold import NoContextReason, ThresholdDecision, judge

logger = logging.getLogger(__name__)

COMPARE_PARSE_ERROR_MESSAGE = "비교 결과를 만들지 못했습니다. 다시 질문해주세요."


class CompareGenerator(Protocol):
    async def generate_compare(
        self,
        query: str,
        chunks_a: Sequence[RetrievedChunk],
        chunks_b: Sequence[RetrievedChunk],
        *,
        display_name_a: str,
        display_name_b: str,
        prompt_version: str,
    ) -> CompareGeneration: ...


@dataclass(frozen=True)
class CompareRequest:
    request_id: str
    question: str
    index_a: ActiveIndex  # 요청 시작 시 확정한 run (구버전 A)
    index_b: ActiveIndex  # 신버전 B
    prompt_version: str
    history: tuple[HistoryMessage, ...] = ()


class ComparePipeline:
    def __init__(
        self,
        retriever: Searcher,
        generator: CompareGenerator,
        retrieval: RetrievalConfig,
        *,
        tau_overrides: Mapping[str, float] | None = None,
        rewriter: QueryRewriter | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.retriever = retriever
        self.generator = generator
        self.retrieval = retrieval
        self.tau_overrides = dict(tau_overrides or {})
        self.rewriter: QueryRewriter = rewriter or SkippingRewriter()
        self.clock = clock

    async def run(
        self, req: CompareRequest, progress: StreamProgress
    ) -> AsyncGenerator[dict[str, Any]]:
        inner = self._run(req, progress)
        try:
            async for event in inner:
                yield event
        except Exception:  # 종결 이벤트 1회 보장 (INV-06)
            logger.exception("stream_internal_error", extra={"request_id": req.request_id})
            yield error_event(
                "INTERNAL_ERROR", INTERNAL_ERROR_MESSAGE, req.request_id, partial=False
            )
        finally:
            await inner.aclose()

    async def _run(
        self, req: CompareRequest, progress: StreamProgress
    ) -> AsyncGenerator[dict[str, Any]]:
        rewrite = await self.rewriter.rewrite(req.question, req.history, request_id=req.request_id)
        progress.latency.rewrite_ms = rewrite.elapsed_ms
        try:
            result_a, result_b = await asyncio.gather(
                self._search(rewrite.query, req.index_a), self._search(rewrite.query, req.index_b)
            )
        except EmbeddingError:
            logger.error("embedding_failed", extra={"request_id": req.request_id}, exc_info=True)
            yield error_event("LLM_ERROR", LLM_ERROR_MESSAGE, req.request_id, partial=False)
            return
        except RetrievalError as exc:
            yield error_event(exc.code, str(exc), req.request_id, partial=False)
            return
        progress.latency.embed_ms = max(result_a.embed_ms, result_b.embed_ms)
        progress.latency.retrieve_ms = max(result_a.retrieve_ms, result_b.retrieve_ms)

        decision_a = self._judge(req, result_a)
        decision_b = self._judge(req, result_b)
        meta = CompareMetaEvent(
            request_id=req.request_id,
            index_a=req.index_a,
            index_b=req.index_b,
            no_context=not (decision_a.passed or decision_b.passed),
            rewritten_query=rewrite.rewritten,
        )
        if meta.no_context:  # INV-07: 생성기를 부르지 않는다
            yield meta.to_dict()
            yield self._done(req, progress, "NO_CONTEXT", NoContextReason.LOW_SIMILARITY).to_dict()
            return

        chunks_a = self._context(result_a, decision_a)
        chunks_b = self._context(result_b, decision_b)
        sources = [source_payload(f"A{rank}", c) for rank, c in enumerate(chunks_a, start=1)]
        sources += [source_payload(f"B{rank}", c) for rank, c in enumerate(chunks_b, start=1)]
        yield replace(meta, sources=sources).to_dict()

        started = self.clock()
        try:
            generation = await self.generator.generate_compare(
                req.question,
                chunks_a,
                chunks_b,
                display_name_a=req.index_a.display_name or req.index_a.source_key,
                display_name_b=req.index_b.display_name or req.index_b.source_key,
                prompt_version=req.prompt_version,
            )
        except CompareParseError:
            logger.error("compare_parse_failed", extra={"request_id": req.request_id})
            yield error_event(
                "COMPARE_PARSE_ERROR", COMPARE_PARSE_ERROR_MESSAGE, req.request_id, partial=False
            )
            return
        except LLMCallError:
            logger.error("compare_llm_failed", extra={"request_id": req.request_id}, exc_info=True)
            yield error_event("LLM_ERROR", LLM_ERROR_MESSAGE, req.request_id, partial=False)
            return
        progress.model = generation.model

        checked = check_compare(
            generation.result,
            count_a=len(chunks_a),
            count_b=len(chunks_b),
            no_evidence_a=not decision_a.passed,
            no_evidence_b=not decision_b.passed,
        )
        logger.info(
            "compare_structured_done",
            extra={
                "request_id": req.request_id,
                "latency_ms": max(0, round((self.clock() - started) * 1000)),
                "attempts": generation.attempts,
                "invalid_citations": checked.invalid_citations,
                "changes_dropped": checked.dropped_changes,
            },
        )
        yield self._done(
            req,
            progress,
            "COMPLETED",
            None,
            model=generation.model,
            finish_reason="stop",
            usage=generation.usage,
            invalid=checked.invalid_citations,
            compare_result=checked.result.model_dump(),
        ).to_dict()

    async def _search(self, query: str, index: ActiveIndex) -> RetrievalResult:
        return await asyncio.to_thread(
            self.retriever.search, query, index.source_key, self.retrieval.top_k, index=index
        )

    def _judge(self, req: CompareRequest, result: RetrievalResult) -> ThresholdDecision:
        source_key = result.index.source_key
        decision = judge(result.chunks, self.retrieval.tau(source_key, self.tau_overrides))
        logger.info(
            "retrieval_done",
            extra={
                "request_id": req.request_id,
                "source_key": source_key,
                "ingest_run_id": result.index.run_id,
                "max_similarity": decision.top1_similarity,
                "chunks_count": len(result.chunks),
                "discarded": result.discarded,
                "latency_ms": result.embed_ms + result.retrieve_ms,
            },
        )
        if not decision.passed:
            logger.info(
                "no_context_triggered",
                extra={
                    "request_id": req.request_id,
                    "source_key": source_key,
                    "max_similarity": decision.top1_similarity,
                    "tau": decision.tau,
                },
            )
        return decision

    def _context(
        self, result: RetrievalResult, decision: ThresholdDecision
    ) -> list[RetrievedChunk]:
        if not decision.passed:
            return []  # 근거 없는 측은 출처·컨텍스트를 넣지 않는다 (정책서 §5.6)
        return select_context(
            result.chunks, decision.tau, self.retrieval.context_budget_tokens
        ).chunks

    def _done(
        self,
        req: CompareRequest,
        progress: StreamProgress,
        status: Any,
        reason: str | None,
        *,
        model: str | None = None,
        finish_reason: str | None = None,
        usage: Any = None,
        invalid: list[str] | None = None,
        compare_result: dict[str, Any] | None = None,
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
            compare_result=compare_result,
        )

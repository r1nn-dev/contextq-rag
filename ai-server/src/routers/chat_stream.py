"""`POST /internal/v1/chat/stream` — 단일·비교 모드 SSE (api-spec §6.1, 부록 B.1·B.2, ADR-003·010).

스트림 전(HTTP 상태): 검증 400(허용되지 않은 비교 쌍 포함) · 토큰 401 · 소스 404/409 ·
모델 불일치 500 · ACTIVE 없음 503 · 동시 처리 초과 503(AI_BUSY, 대기열 없음).
그 뒤의 오류는 모두 `error` 이벤트다(INV-09). 비교 모드는 요청 1개가 슬롯 1개를 쓰고,
30초(`stream.compare_max_duration_seconds`)를 넘으면 `error(UPSTREAM_TIMEOUT)`로 끝낸다.
"""

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from src.domain.chat_stream import ChatStreamRequest, DoneEvent, error_event
from src.pipeline.compare import CompareRequest
from src.pipeline.prompts import load_template
from src.pipeline.single import (
    INTERNAL_ERROR_MESSAGE,
    SingleRequest,
    StreamProgress,
    question_digest,
)
from src.routers.auth import verify_internal_token
from src.routers.errors import ApiError, request_id_of
from src.routers.services import ChatServices, get_services
from src.routers.sse import pump

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/internal/v1", tags=["internal"], dependencies=[Depends(verify_internal_token)]
)

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


class Slot:
    """동시 처리 슬롯 1개. 스트림 종료·응답 정리 어느 쪽에서 불러도 한 번만 반납한다."""

    def __init__(self, semaphore: asyncio.Semaphore) -> None:
        self._semaphore = semaphore
        self._held = True

    def release(self) -> None:
        if self._held:
            self._held = False
            self._semaphore.release()


async def _acquire(semaphore: asyncio.Semaphore) -> Slot:
    """대기 없이 즉시 거절 (정책서 §8.1).

    잠기지 않은 세마포어의 `acquire()`는 양보 없이 끝나므로 확인과 차감 사이에 끼어들 수 없다.
    """
    if semaphore.locked():
        raise ApiError(503, "AI_BUSY", "시스템이 혼잡합니다. 잠시 후 다시 시도해 주세요.")
    await semaphore.acquire()
    return Slot(semaphore)


def _max_duration_terminal(req: SingleRequest, progress: StreamProgress, clock: Any) -> Any:
    """120초 상한 — 토큰 ≥ 1: PARTIAL, 0개: FAILED (statusReason=MAX_DURATION, 정책서 §10.2)."""

    def build(meta_sent: bool) -> dict[str, Any]:
        logger.warning(
            "stream_aborted", extra={"request_id": req.request_id, "reason": "MAX_DURATION"}
        )
        if not meta_sent:
            return error_event(
                "INTERNAL_ERROR", INTERNAL_ERROR_MESSAGE, req.request_id, partial=False
            )
        progress.latency.total_ms = progress.elapsed_ms(clock())
        return DoneEvent(
            status="PARTIAL" if progress.tokens else "FAILED",
            latency=progress.latency,
            status_reason="MAX_DURATION",
            model=progress.model,
            prompt_version=req.prompt_version,
        ).to_dict()

    return build


UPSTREAM_TIMEOUT_MESSAGE = "비교 결과가 제한 시간 안에 만들어지지 않았습니다. 다시 질문해주세요."


def _compare_timeout_terminal(req: CompareRequest) -> Any:
    """비교 모드 30초 상한 — meta 전후 모두 `error(UPSTREAM_TIMEOUT, partial=false)` (§10.2)"""

    def build(meta_sent: bool) -> dict[str, Any]:
        logger.warning(
            "stream_aborted",
            extra={
                "request_id": req.request_id,
                "reason": "COMPARE_TIMEOUT",
                "meta_sent": meta_sent,
            },
        )
        return error_event(
            "UPSTREAM_TIMEOUT", UPSTREAM_TIMEOUT_MESSAGE, req.request_id, partial=False
        )

    return build


def _sse_response(events: AsyncIterator[str], slot: Slot, request_id: str) -> StreamingResponse:
    async def body_iterator() -> AsyncIterator[str]:
        try:
            async for chunk in events:
                yield chunk
        except asyncio.CancelledError:
            logger.info(
                "stream_aborted", extra={"request_id": request_id, "reason": "CLIENT_ABORTED"}
            )
            raise
        finally:
            slot.release()

    return StreamingResponse(
        body_iterator(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
        background=BackgroundTask(slot.release),  # 스트림을 시작하지 못한 경우의 안전망
    )


async def _compare_stream(
    body: ChatStreamRequest, request_id: str, services: ChatServices
) -> StreamingResponse:
    if services.compare is None or services.pairs is None:
        raise ApiError(500, "INTERNAL_ERROR", "비교 모드가 설정되지 않았습니다")
    prompt_version = body.prompt_version or services.config.generation.compare_prompt_version
    load_template(prompt_version)  # 없는 버전 → 400 (PromptNotFoundError)
    assert body.source_key_a is not None and body.source_key_b is not None  # COMPARE 검증 통과
    allowed = await asyncio.to_thread(services.pairs.allows, body.source_key_a, body.source_key_b)
    if not allowed:  # 정책서 §3.2 — 정의된 쌍, A = 구버전 · B = 신버전 순서만
        raise ApiError(400, "INVALID_REQUEST", "허용되지 않은 비교 쌍입니다")
    index_a = await asyncio.to_thread(services.retriever.prepare, body.source_key_a)
    index_b = await asyncio.to_thread(services.retriever.prepare, body.source_key_b)
    slot = await _acquire(services.slots)

    pipeline = services.compare
    progress = StreamProgress(started=pipeline.clock())
    req = CompareRequest(
        request_id, body.question, index_a, index_b, prompt_version, tuple(body.history)
    )
    logger.info(
        "query_received",
        extra={
            "request_id": request_id,
            "mode": body.mode,
            "source_key_a": index_a.source_key,
            "source_key_b": index_b.source_key,
            "ingest_run_id_a": index_a.run_id,
            "ingest_run_id_b": index_b.run_id,
            "has_history": bool(body.history),
            **question_digest(body.question),
        },
    )
    stream_config = services.config.stream
    events = pump(
        pipeline.run(req, progress),
        heartbeat_seconds=stream_config.heartbeat_seconds,
        max_duration_seconds=stream_config.compare_max_duration_seconds,
        on_timeout=_compare_timeout_terminal(req),
        clock=time.monotonic,
    )
    return _sse_response(events, slot, request_id)


@router.post("/chat/stream", response_class=StreamingResponse)
async def chat_stream(
    body: ChatStreamRequest,
    request: Request,
    services: Annotated[ChatServices, Depends(get_services)],
) -> StreamingResponse:
    request_id = body.request_id or request_id_of(request)
    if body.mode == "COMPARE":
        return await _compare_stream(body, request_id, services)
    prompt_version = body.prompt_version or services.config.generation.prompt_version
    load_template(prompt_version)  # 없는 버전 → 400 (PromptNotFoundError)
    assert body.source_key is not None  # SINGLE 검증 통과
    index = await asyncio.to_thread(services.retriever.prepare, body.source_key)
    slot = await _acquire(services.slots)

    clock = services.pipeline.clock
    progress = StreamProgress(started=clock())
    req = SingleRequest(request_id, body.question, index, prompt_version, tuple(body.history))
    logger.info(
        "query_received",
        extra={
            "request_id": request_id,
            "source_key": index.source_key,
            "ingest_run_id": index.run_id,
            "mode": body.mode,
            "has_history": bool(body.history),
            **question_digest(body.question),
        },
    )
    stream_config = services.config.stream
    events = pump(
        services.pipeline.run(req, progress),
        heartbeat_seconds=stream_config.heartbeat_seconds,
        max_duration_seconds=stream_config.max_duration_seconds,
        on_timeout=_max_duration_terminal(req, progress, clock),
        clock=time.monotonic,
    )
    return _sse_response(events, slot, request_id)

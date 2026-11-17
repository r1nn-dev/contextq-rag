"""클라이언트 취소 전파 — 연결이 끊기면 생성 스트림(OpenAI)을 닫는다 (rag-pipeline §3.6, R-4-4)."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from src.config.rag_config import load_rag_config
from src.pipeline.single import SingleModePipeline, StreamProgress
from src.routers.sse import pump
from tests.unit.test_pipeline_single import REQUEST, FakeGenerator, FakeSearcher, FakeStream, chunk


class SlowStream(FakeStream):
    """토큰 사이에 지연이 있는 생성 스트림 — 생성 도중 취소를 재현한다."""

    async def _gen(self) -> AsyncIterator[str]:
        for token in self.tokens:
            await asyncio.sleep(0.05)
            self.model = "gpt-4o-mini-2024-07-18"
            yield token
        self.finish_reason = "stop"


def stream_pump(stream: FakeStream) -> AsyncIterator[str]:
    pipeline = SingleModePipeline(
        FakeSearcher([chunk(1, 0.9)]), FakeGenerator(stream), load_rag_config().retrieval
    )
    return pump(
        pipeline.run(REQUEST, StreamProgress(started=0.0)),
        heartbeat_seconds=10,
        max_duration_seconds=30,
        on_timeout=lambda meta_sent: {},
    )


async def test_closing_response_iterator_closes_llm_stream() -> None:
    stream = SlowStream(["a ", "b ", "c ", "d "])
    body: Any = stream_pump(stream)

    assert '"meta"' in await body.__anext__()
    assert '"token"' in await body.__anext__()
    await body.aclose()  # 응답 이터레이터 종료 (연결 끊김)

    assert stream.closed


async def test_cancelling_response_task_closes_llm_stream() -> None:
    stream = SlowStream(["a "] * 50)
    received: list[str] = []

    async def consume() -> None:
        async for part in stream_pump(stream):
            received.append(part)

    task = asyncio.create_task(consume())
    while len(received) < 2:  # meta + 첫 token
        await asyncio.sleep(0.01)
    task.cancel()  # Starlette가 연결 끊김을 감지하면 응답 태스크를 취소한다
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert stream.closed
    assert len(received) < 50

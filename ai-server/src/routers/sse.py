"""SSE 전송 — 하트비트·최대 시간 (정책서 §2.1, api-spec.md §6.1).

이벤트 생산(파이프라인)은 별도 태스크에서 돌리고 큐로 받는다. 소비 루프는
- 하트비트 간격 동안 이벤트가 없으면 `: ping`을 보내고,
- 최대 시간이 지나면 생산 태스크를 취소한 뒤 `on_timeout`이 만든 종결 이벤트를 보낸다.
생산을 직접 `wait_for`로 감싸면 타임아웃 때 진행 중인 생성 호출까지 취소되므로 쓰지 않는다.
"""

import asyncio
import contextlib
import json
import time
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from typing import Any

PING = ": ping\n\n"


def sse_data(event: dict[str, Any]) -> str:
    """`data: {json}\\n\\n` — 이벤트 이름은 JSON의 `event` 필드 (api-spec.md §6.1 응답 예시)."""
    return f"data: {json.dumps(event, ensure_ascii=False, separators=(',', ':'))}\n\n"


async def pump(
    events: AsyncGenerator[dict[str, Any]],
    *,
    heartbeat_seconds: float,
    max_duration_seconds: float,
    on_timeout: Callable[[bool], dict[str, Any]],
    clock: Callable[[], float] = time.monotonic,
) -> AsyncIterator[str]:
    """이벤트를 SSE 문자열로 내보낸다. `on_timeout(meta_sent)`은 최대 시간 종결 이벤트를 만든다."""
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    deadline = clock() + max_duration_seconds

    async def produce() -> None:
        try:
            async for event in events:
                queue.put_nowait(event)
        finally:
            queue.put_nowait(None)  # 끝 표시 (취소돼도 넣는다)

    producer = asyncio.create_task(produce())
    meta_sent = False
    try:
        while True:
            remaining = deadline - clock()
            if remaining <= 0:
                await _stop(producer)
                yield sse_data(on_timeout(meta_sent))
                return
            try:
                item = await asyncio.wait_for(
                    queue.get(), timeout=min(heartbeat_seconds, remaining)
                )
            except TimeoutError:
                if clock() < deadline:
                    yield PING
                continue
            if item is None:
                producer.result()  # 생산 중 예외가 있었다면 여기서 드러난다
                return
            meta_sent = meta_sent or item.get("event") == "meta"
            yield sse_data(item)
    finally:
        await _stop(producer)
        await events.aclose()


async def _stop(task: asyncio.Task[None]) -> None:
    if not task.done():
        task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

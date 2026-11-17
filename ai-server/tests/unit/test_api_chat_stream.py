"""`POST /internal/v1/chat/stream` — 스트림 전 HTTP 오류, SSE 계약, 동시성·하트비트·최대 시간."""

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.config.rag_config import load_rag_config
from src.config.settings import Settings
from src.main import create_app
from src.pipeline.single import SingleModePipeline
from src.retrieval.errors import SourceNotFoundError
from src.retrieval.pointers import ActiveIndex
from src.retrieval.search import RetrievalResult
from src.routers.services import ChatServices, get_services
from src.routers.sse import PING, pump
from tests.contract.sse_contract import validate_stream
from tests.unit.test_pipeline_single import INDEX, FakeGenerator, FakeStream, chunk

TOKEN = "t0ken"
HEADERS = {"X-Internal-Token": TOKEN}
BODY = {"requestId": "req-9", "mode": "SINGLE", "sourceKey": "langchain_v1x", "question": "q?"}


class FakeRetriever:
    def __init__(self, chunks: list[Any], prepare_error: Exception | None = None) -> None:
        self.chunks = chunks
        self.prepare_error = prepare_error

    def prepare(self, source_key: str) -> ActiveIndex:
        if self.prepare_error:
            raise self.prepare_error
        return INDEX

    def search(
        self, query: str, source_key: str, top_k: int = 5, *, index: ActiveIndex | None = None
    ) -> RetrievalResult:
        assert index is INDEX
        return RetrievalResult(INDEX, self.chunks, embed_ms=5, retrieve_ms=7)


def services(
    *, chunks: list[Any] | None = None, slots: int = 20, prepare_error: Exception | None = None,
    stream: FakeStream | None = None,
) -> ChatServices:  # fmt: skip
    config = load_rag_config()
    retriever = FakeRetriever([chunk(1, 0.9)] if chunks is None else chunks, prepare_error)
    generator = FakeGenerator(stream or FakeStream(["LangChain v1.x 기준 ", "답 [1]"]))
    pipeline = SingleModePipeline(retriever, generator, config.retrieval)
    return ChatServices(config, None, retriever, pipeline, asyncio.Semaphore(slots))  # type: ignore[arg-type]


def client_for(fake: ChatServices) -> TestClient:
    app = create_app(Settings(_env_file=None, internal_token=TOKEN))  # type: ignore[call-arg]
    app.dependency_overrides[get_services] = lambda: fake
    return TestClient(app)


def parse_sse(text: str) -> list[dict[str, Any]]:
    return [
        json.loads(block.removeprefix("data: "))
        for block in text.split("\n\n")
        if block.startswith("data: ")
    ]


def test_streams_contract_valid_events() -> None:
    response = client_for(services()).post("/internal/v1/chat/stream", json=BODY, headers=HEADERS)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    events = parse_sse(response.text)
    validate_stream(events, leg="upstream")
    assert [e["event"] for e in events] == ["meta", "token", "token", "done"]
    assert events[0]["requestId"] == "req-9"
    assert events[-1]["promptVersion"] == "single_v1"  # 요청에 없으면 rag.yaml 기본값


def test_request_id_falls_back_to_header() -> None:
    body = {k: v for k, v in BODY.items() if k != "requestId"}

    response = client_for(services()).post(
        "/internal/v1/chat/stream", json=body, headers={**HEADERS, "X-Request-Id": "from-nginx"}
    )

    assert parse_sse(response.text)[0]["requestId"] == "from-nginx"


def test_low_similarity_stream_over_http() -> None:
    fake = services(chunks=[chunk(1, 0.1)])

    events = parse_sse(
        client_for(fake).post("/internal/v1/chat/stream", json=BODY, headers=HEADERS).text
    )

    validate_stream(events, leg="upstream")
    assert events[-1]["statusReason"] == "LOW_SIMILARITY"
    assert fake.pipeline.generator.calls == []  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("fake", "body", "headers", "status", "code"),
    [
        (services(), BODY, {}, 401, "INTERNAL_UNAUTHORIZED"),
        (services(), {**BODY, "promptVersion": "single_v9"}, HEADERS, 400, "INVALID_REQUEST"),
        (services(), {**BODY, "question": ""}, HEADERS, 400, "INVALID_REQUEST"),
        (services(prepare_error=SourceNotFoundError("x")), BODY, HEADERS, 404, "SOURCE_NOT_FOUND"),
        (services(slots=0), BODY, HEADERS, 503, "AI_BUSY"),
    ],
)
def test_pre_stream_errors_are_http_statuses(
    fake: ChatServices, body: dict[str, Any], headers: dict[str, str], status: int, code: str
) -> None:
    response = client_for(fake).post("/internal/v1/chat/stream", json=body, headers=headers)

    assert response.status_code == status
    assert response.json()["code"] == code


def test_slot_is_returned_after_each_stream() -> None:
    fake = services(slots=1)
    client = client_for(fake)

    for _ in range(3):  # 슬롯이 1개여도 순차 요청은 모두 처리된다
        assert (
            client.post("/internal/v1/chat/stream", json=BODY, headers=HEADERS).status_code == 200
        )
    assert not fake.slots.locked()


# --- 하트비트·최대 시간 -------------------------------------------------------------


async def slow_events(delays: list[float], closed: list[bool]) -> AsyncGenerator[dict[str, Any]]:
    try:
        yield {"event": "meta", "requestId": "r"}
        for i, delay in enumerate(delays):
            await asyncio.sleep(delay)
            yield {"event": "token", "t": str(i)}
        yield {"event": "done", "status": "COMPLETED"}
    finally:
        closed.append(True)


def timeout_terminal(meta_sent: bool) -> dict[str, Any]:
    return {"event": "done", "status": "PARTIAL", "statusReason": "MAX_DURATION", "meta": meta_sent}


async def test_heartbeat_is_sent_while_waiting() -> None:
    closed: list[bool] = []
    out = [
        chunk
        async for chunk in pump(
            slow_events([0.25], closed),
            heartbeat_seconds=0.1,
            max_duration_seconds=5,
            on_timeout=timeout_terminal,
        )
    ]

    assert out[0].startswith("data: ") and PING in out[1:3]
    assert out[-1].startswith("data: ") and '"done"' in out[-1]
    assert closed == [True]


async def test_max_duration_ends_with_terminal_and_stops_producer() -> None:
    closed: list[bool] = []
    out = [
        chunk
        async for chunk in pump(
            slow_events([10.0], closed),
            heartbeat_seconds=0.05,
            max_duration_seconds=0.2,
            on_timeout=timeout_terminal,
        )
    ]

    last = json.loads(out[-1].removeprefix("data: "))
    assert last == {"event": "done", "status": "PARTIAL", "statusReason": "MAX_DURATION",
                    "meta": True}  # fmt: skip
    assert closed == [True]  # 생산 쪽(생성 스트림 포함) 정리됨

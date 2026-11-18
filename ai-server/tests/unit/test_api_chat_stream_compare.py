"""내부 스트림 비교 모드 — 스트림 전 검증, SSE 계약, 30초 상한 (api-spec §6.1)."""

import asyncio
from collections.abc import Sequence
from typing import Any

import pytest

from src.config.rag_config import load_rag_config
from src.domain.retrieval import RetrievedChunk
from src.pipeline.compare import ComparePipeline
from src.pipeline.compare_generator import CompareGeneration
from src.pipeline.single import SingleModePipeline
from src.retrieval.errors import SourceUnavailableError
from src.retrieval.pairs import ComparePairCatalog, StaticPairs
from src.retrieval.pointers import ActiveIndex
from src.retrieval.search import RetrievalResult
from src.routers.services import ChatServices
from tests.contract.sse_contract import validate_stream
from tests.unit.test_api_chat_stream import HEADERS, client_for, parse_sse
from tests.unit.test_pipeline_compare import INDEX_A, INDEX_B, side_result
from tests.unit.test_pipeline_single import FakeGenerator, FakeStream, chunk

BODY = {
    "requestId": "req-c",
    "mode": "COMPARE",
    "sourceKeyA": "langchain_v03",
    "sourceKeyB": "langchain_v1x",
    "question": "에이전트 생성 방식이 어떻게 바뀌었나요?",
}
URL = "/internal/v1/chat/stream"


class CompareRetriever:
    def __init__(self, prepare_errors: dict[str, Exception] | None = None) -> None:
        self.prepare_errors = prepare_errors or {}
        self.indexes = {"langchain_v03": INDEX_A, "langchain_v1x": INDEX_B}

    def prepare(self, source_key: str) -> ActiveIndex:
        if source_key in self.prepare_errors:
            raise self.prepare_errors[source_key]
        return self.indexes[source_key]

    def search(
        self, query: str, source_key: str, top_k: int = 5, *, index: ActiveIndex | None = None
    ) -> RetrievalResult:
        assert index is self.indexes[source_key]
        return RetrievalResult(index, [chunk(1, 0.9)], embed_ms=5, retrieve_ms=7)


class SlowCompareGenerator:
    def __init__(self, delay: float = 0) -> None:
        self.delay = delay
        self.calls = 0

    async def generate_compare(
        self, query: str, chunks_a: Sequence[RetrievedChunk], chunks_b: Sequence[RetrievedChunk],
        **_: Any,
    ) -> CompareGeneration:  # fmt: skip
        self.calls += 1
        await asyncio.sleep(self.delay)
        return CompareGeneration(side_result(changes=[]), "gpt-4o-mini", None, 1)


def services(
    *, slots: int = 20, prepare_errors: dict[str, Exception] | None = None,
    delay: float = 0, compare_seconds: float = 30,
) -> ChatServices:  # fmt: skip
    config = load_rag_config()
    config = config.model_copy(
        update={"stream": config.stream.model_copy(
            update={"compare_max_duration_seconds": compare_seconds, "heartbeat_seconds": 5})}
    )  # fmt: skip
    retriever = CompareRetriever(prepare_errors)
    single = SingleModePipeline(retriever, FakeGenerator(FakeStream(["x"])), config.retrieval)  # type: ignore[arg-type]
    compare = ComparePipeline(retriever, SlowCompareGenerator(delay), config.retrieval)  # type: ignore[arg-type]
    pairs = StaticPairs(frozenset({("langchain_v03", "langchain_v1x")}))
    return ChatServices(config, None, retriever, single, asyncio.Semaphore(slots), compare, pairs)  # type: ignore[arg-type]


def test_compare_stream_is_contract_valid_without_tokens() -> None:
    response = client_for(services()).post(URL, json=BODY, headers=HEADERS)

    assert response.status_code == 200
    events = parse_sse(response.text)
    validate_stream(events, leg="upstream")
    assert [e["event"] for e in events] == ["meta", "done"]
    assert [s["rank"] for s in events[0]["sources"]] == ["A1", "B1"]
    assert events[1]["invalidCitations"] == ["B2"]  # B측 출처는 1개 → B2는 후처리에서 제거
    assert events[1]["promptVersion"] == "compare_v1"  # rag.yaml 기본값


@pytest.mark.parametrize(
    ("body", "code_status"),
    [
        ({**BODY, "sourceKeyB": None}, 400),  # B 누락
        ({**BODY, "sourceKeyB": "langchain_v03"}, 400),  # 같은 소스
        ({**BODY, "sourceKeyA": "langchain_v1x", "sourceKeyB": "langchain_v03"}, 400),  # 순서 반대
        ({**BODY, "promptVersion": "compare_v9"}, 400),  # 없는 프롬프트
    ],
)
def test_invalid_compare_requests_are_400(body: dict[str, Any], code_status: int) -> None:
    response = client_for(services()).post(URL, json=body, headers=HEADERS)

    assert response.status_code == code_status
    assert response.json()["code"] == "INVALID_REQUEST"


def test_each_side_gets_pre_stream_source_checks() -> None:
    fake = services(prepare_errors={"langchain_v1x": SourceUnavailableError("off")})

    response = client_for(fake).post(URL, json=BODY, headers=HEADERS)

    assert (response.status_code, response.json()["code"]) == (409, "SOURCE_UNAVAILABLE")
    assert not fake.slots.locked()


def test_compare_uses_one_concurrency_slot() -> None:
    busy = client_for(services(slots=0)).post(URL, json=BODY, headers=HEADERS)
    fake = services(slots=1)
    ok = client_for(fake).post(URL, json=BODY, headers=HEADERS)

    assert (busy.status_code, busy.json()["code"]) == (503, "AI_BUSY")
    assert ok.status_code == 200 and not fake.slots.locked()


def test_compare_over_time_limit_ends_with_upstream_timeout() -> None:
    fake = services(delay=1.0, compare_seconds=0.2)

    events = parse_sse(client_for(fake).post(URL, json=BODY, headers=HEADERS).text)

    validate_stream(events, leg="upstream")
    assert [e["event"] for e in events] == ["meta", "error"]
    assert (events[-1]["code"], events[-1]["partial"]) == ("UPSTREAM_TIMEOUT", False)
    assert not fake.slots.locked()


def test_single_mode_still_requires_source_key() -> None:
    body = {"mode": "SINGLE", "question": "q?"}

    response = client_for(services()).post(URL, json=body, headers=HEADERS)

    assert response.status_code == 400


class FakeSession:
    def __init__(self, rows: list[tuple[str, str]]) -> None:
        self.rows = rows
        self.calls = 0

    def __enter__(self) -> "FakeSession":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, _query: object) -> Any:
        self.calls += 1
        return iter(self.rows)


def test_pair_catalog_reads_the_immutable_table_once_and_keeps_order() -> None:
    session = FakeSession([("langchain_v03", "langchain_v1x")])
    catalog = ComparePairCatalog(lambda: session)  # type: ignore[arg-type,return-value]

    assert catalog.allows("langchain_v03", "langchain_v1x")
    assert not catalog.allows("langchain_v1x", "langchain_v03")  # A = 구버전 순서만
    assert session.calls == 1

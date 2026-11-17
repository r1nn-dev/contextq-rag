"""내부 API 공통 — 토큰 검증(ADR-012)·스트림 전 오류 본문(api-spec §6.1)·요청/이벤트 스키마."""

from datetime import date

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.config.settings import Settings
from src.domain.chat_stream import (
    ChatStreamRequest,
    DoneEvent,
    Latency,
    MetaEvent,
    error_event,
    source_payload,
    token_event,
)
from src.domain.retrieval import RetrievedChunk
from src.main import create_app
from src.retrieval.errors import IndexNotActiveError
from src.routers.auth import verify_internal_token
from tests.contract.sse_contract import validate_event, validate_stream

TOKEN = "test-internal-token"


def make_app(token: str = TOKEN) -> FastAPI:
    app = create_app(Settings(_env_file=None, internal_token=token))  # type: ignore[call-arg]

    @app.post("/internal/v1/_probe", dependencies=[Depends(verify_internal_token)])
    async def probe(body: ChatStreamRequest) -> dict[str, str]:
        if body.source_key == "missing_index":
            raise IndexNotActiveError("ACTIVE run이 없습니다")
        return {"ok": body.question}

    return app


BODY = {"requestId": "r-1", "mode": "SINGLE", "sourceKey": "langchain_v1x", "question": " 질문 "}


def test_valid_token_passes_and_question_is_trimmed() -> None:
    client = TestClient(make_app())

    response = client.post("/internal/v1/_probe", json=BODY, headers={"X-Internal-Token": TOKEN})

    assert response.status_code == 200
    assert response.json() == {"ok": "질문"}


@pytest.mark.parametrize("headers", [{}, {"X-Internal-Token": "wrong"}])
def test_missing_or_wrong_token_is_401(headers: dict[str, str]) -> None:
    client = TestClient(make_app())

    response = client.post(
        "/internal/v1/_probe", json=BODY, headers={**headers, "X-Request-Id": "rid-7"}
    )

    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "INTERNAL_UNAUTHORIZED"
    assert body["request_id"] == "rid-7"
    assert body["timestamp"].endswith("Z")
    assert set(body) == {"code", "message", "request_id", "timestamp"}


def test_server_without_token_rejects_everything() -> None:
    client = TestClient(make_app(token=""))

    response = client.post("/internal/v1/_probe", json=BODY, headers={"X-Internal-Token": ""})

    assert response.status_code == 401


def test_health_does_not_need_token() -> None:
    assert TestClient(make_app()).get("/internal/v1/health").status_code == 200


@pytest.mark.parametrize(
    "patch",
    [
        {"question": "   "},
        {"question": "x" * 1001},
        {"sourceKey": None},
        {"mode": "COMPARE"},
        {"history": [{"role": "user", "content": "a"}] * 7},
        {"history": [{"role": "system", "content": "a"}]},
    ],
)
def test_invalid_request_is_400_with_error_body(patch: dict[str, object]) -> None:
    client = TestClient(make_app())

    response = client.post(
        "/internal/v1/_probe", json={**BODY, **patch}, headers={"X-Internal-Token": TOKEN}
    )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_REQUEST"


def test_retrieval_errors_map_to_their_status() -> None:
    client = TestClient(make_app())

    response = client.post(
        "/internal/v1/_probe",
        json={**BODY, "sourceKey": "missing_index"},
        headers={"X-Internal-Token": TOKEN},
    )

    assert response.status_code == 503
    assert response.json()["code"] == "INDEX_NOT_ACTIVE"


def test_request_accepts_optional_fields_absent() -> None:
    request = ChatStreamRequest.model_validate({"sourceKey": "langchain_v03", "question": "q"})

    assert (request.request_id, request.prompt_version, request.history) == (None, None, [])
    with pytest.raises(ValidationError):
        ChatStreamRequest.model_validate({"question": "q"})


CHUNK = RetrievedChunk(
    chunk_id="c",
    content="x",
    permalink="https://github.com/o/r/blob/" + "a" * 40 + "/a.mdx?plain=1#L1-L2",
    source_key="langchain_v1x",
    file_path="a.mdx",
    heading_path="A > B",
    token_count=3,
    site_url="https://docs.langchain.com/oss/python/a",
    similarity=0.812345,
)


def test_events_satisfy_upstream_contract() -> None:
    meta = MetaEvent("r-1", "langchain_v1x", 3, "b" * 40, date(2026, 11, 17), False,
                     [source_payload(1, CHUNK)]).to_dict()  # fmt: skip
    done = DoneEvent(
        "COMPLETED",
        Latency(None, 80, 120, 900, 3000),
        finish_reason="stop",
        usage={"prompt": 10, "completion": 5},
        model="gpt-4o-mini-2024-07-18",
        prompt_version="single_v1",
    ).to_dict()

    validate_stream([meta, token_event("답 [1]"), done], leg="upstream")
    assert meta["sources"][0]["similarity"] == 0.8123
    validate_event(error_event("LLM_ERROR", "오류", "r-1", partial=False), leg="upstream")


def test_no_context_meta_drops_sources_and_unknown_snapshot_fields() -> None:
    meta = MetaEvent("r-1", "langchain_v03", 1, None, None, True, [source_payload(1, CHUNK)])

    data = meta.to_dict()
    assert data["sources"] == [] and "commitSha" not in data and "ingestedAt" not in data
    validate_event(data, leg="upstream")

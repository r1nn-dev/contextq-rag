"""내부 소스 조회·포인터 reload — api-spec.md §6.3·§6.5."""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from src.config.settings import Settings
from src.domain.tables import ComparePair, IndexPointer, IngestRun, Source
from src.ingest.store import ChromaVectorStore
from src.main import create_app
from src.retrieval.pointers import PointerCache
from src.routers.services import IndexServices
from tests.unit.test_retrieval_pointers import SHA, _active

V03, V1X = "langchain_v03", "langchain_v1x"
HEADERS = {"X-Internal-Token": "tok"}


@pytest.fixture()
def index(session_factory: sessionmaker[Session], tmp_path: Path) -> IndexServices:
    return IndexServices(
        session_factory, ChromaVectorStore(tmp_path / "chroma"), PointerCache(session_factory)
    )


def client_with(index: IndexServices) -> TestClient:
    app = create_app(Settings(_env_file=None, internal_token="tok"))  # type: ignore[call-arg]
    app.state.index_services = index
    return TestClient(app)


def test_sources_lists_catalog_active_runs_and_pairs(
    session_factory: sessionmaker[Session], index: IndexServices
) -> None:
    with session_factory() as db:
        run_id = _active(db, V1X)
        db.add(ComparePair(source_key_a=V03, source_key_b=V1X))
        source = db.scalar(select(Source).where(Source.source_key == V03))
        assert source is not None
        source.enabled = False  # 비활성 소스도 목록에 나온다
        db.commit()

    response = client_with(index).get("/internal/v1/sources", headers=HEADERS)

    assert response.status_code == 200
    assert response.json() == {
        "sources": [
            {
                "sourceKey": V03,
                "framework": "langchain",
                "versionLabel": "v0.3",
                "displayName": "LangChain v0.3",
                "enabled": False,
                "activeRunId": None,
                "commitSha": None,
                "ingestedAt": None,
                "chunkCount": None,
            },
            {
                "sourceKey": V1X,
                "framework": "langchain",
                "versionLabel": "v1.x",
                "displayName": "LangChain v1.x",
                "enabled": True,
                "activeRunId": run_id,
                "commitSha": SHA,
                "ingestedAt": "2026-11-17",
                "chunkCount": 120,
            },
        ],
        "comparePairs": [{"sourceKeyA": V03, "sourceKeyB": V1X}],
    }


def test_sources_requires_internal_token(index: IndexServices) -> None:
    response = client_with(index).get("/internal/v1/sources")

    assert response.status_code == 401


def test_reload_switches_cached_pointer_immediately(
    session_factory: sessionmaker[Session], index: IndexServices
) -> None:
    with session_factory() as db:
        old = _active(db, V1X)
    assert index.pointers.get(V1X).run_id == old  # 30초 캐시에 이전 run

    with session_factory() as db:
        new = _active(db, V1X)  # make activate-index
    assert index.pointers.get(V1X).run_id == old  # 아직 캐시

    response = client_with(index).post(
        "/internal/v1/index/reload", json={"sourceKey": V1X}, headers=HEADERS
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["sourceKey"], body["activeRunId"]) == (V1X, new)
    assert body["reloadedAt"].endswith("Z")
    assert index.pointers.get(V1X).run_id == new  # 다음 질의부터 새 run


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [
        ({"sourceKey": "react_v18"}, 404, "SOURCE_NOT_FOUND"),
        ({"sourceKey": V03}, 503, "INDEX_NOT_ACTIVE"),
        ({}, 400, "INVALID_REQUEST"),
    ],
)
def test_reload_errors(index: IndexServices, body: dict[str, str], status: int, code: str) -> None:
    response = client_with(index).post("/internal/v1/index/reload", json=body, headers=HEADERS)

    assert response.status_code == status
    assert response.json()["code"] == code


def test_reload_disabled_source_is_409(
    session_factory: sessionmaker[Session], index: IndexServices
) -> None:
    with session_factory() as db:
        _active(db, V03)
        source = db.scalar(select(Source).where(Source.source_key == V03))
        assert source is not None
        source.enabled = False
        db.commit()

    response = client_with(index).post(
        "/internal/v1/index/reload", json={"sourceKey": V03}, headers=HEADERS
    )

    assert (response.status_code, response.json()["code"]) == (409, "SOURCE_UNAVAILABLE")


def _run(db: Session, status: str, day: int, **extra: object) -> int:
    run = IngestRun(
        source_key=V1X,
        status=status,
        accept_drift=False,
        created_at=datetime(2026, 11, day, 1, 0, tzinfo=UTC),
        started_at=datetime(2026, 11, day, 2, 0, tzinfo=UTC),
        **extra,
    )
    db.add(run)
    db.flush()
    return run.id


def test_index_status_lists_active_run_details_and_recent_runs(
    session_factory: sessionmaker[Session], index: IndexServices
) -> None:
    with session_factory() as db:
        old = [_run(db, "SUPERSEDED", day) for day in (1, 2, 3)]
        failed = _run(db, "FAILED", 10, failure_stage="VALIDATING", failure_reason="drift")
        superseded = _run(db, "SUPERSEDED", 11)
        active = _run(
            db,
            "ACTIVE",
            12,
            commit_sha=SHA,
            chunk_strategy="C",
            chunk_count=700,
            prev_chunk_count=650,
            embedding_model="text-embedding-3-small",
            embedding_tokens=2_150_000,
            embedding_cost_usd=Decimal("0.043000"),
            ingest_duration_ms=48_500,
            completed_at=datetime(2026, 11, 12, 2, 1, tzinfo=UTC),
        )
        db.add(IndexPointer(source_key=V1X, active_run_id=active))
        db.commit()

    response = client_with(index).get("/internal/v1/index/status", headers=HEADERS)

    assert response.status_code == 200
    v03, v1x = response.json()["sources"]
    assert v03 == {
        "sourceKey": V03,
        "displayName": "LangChain v0.3",
        "enabled": True,
        "activeRun": None,
        "recentRuns": [],
    }
    assert v1x["activeRun"] == {
        "ingestRunId": active,
        "status": "ACTIVE",
        "commitSha": SHA,
        "chunkStrategy": "C",
        "chunkCount": 700,
        "prevChunkCount": 650,
        "embeddingModel": "text-embedding-3-small",
        "embeddingTokens": 2_150_000,
        "embeddingCostUsd": 0.043,
        "ingestDurationMs": 48_500,
        "startedAt": "2026-11-12T02:00:00Z",
        "completedAt": "2026-11-12T02:01:00Z",
    }
    runs = v1x["recentRuns"]
    assert [r["ingestRunId"] for r in runs] == [active, superseded, failed, old[2], old[1]]
    assert runs[2] == {
        "ingestRunId": failed, "status": "FAILED", "startedAt": "2026-11-10T02:00:00Z",
        "failureStage": "VALIDATING",
    }  # fmt: skip
    assert "failureStage" not in runs[0]  # FAILED만 실패 단계를 넣는다


def test_index_status_requires_internal_token(index: IndexServices) -> None:
    assert client_with(index).get("/internal/v1/index/status").status_code == 401

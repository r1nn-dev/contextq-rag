"""내부 헬스 — 소스별 ACTIVE(포인터 + 컬렉션)·Chroma·DB (api-spec §6.2), /docs 노출."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from src.config.settings import Settings
from src.domain.tables import Source
from src.ingest.store import ChromaVectorStore
from src.main import create_app
from src.retrieval.pointers import PointerCache
from src.routers.services import IndexServices
from tests.unit.test_retrieval_pointers import _active

V03, V1X = "langchain_v03", "langchain_v1x"


def client_with(index: IndexServices | None, profile: str = "local") -> TestClient:
    settings = Settings(_env_file=None, app_profile=profile, internal_token="tok")  # type: ignore[call-arg]
    app = create_app(settings)
    app.state.index_services = index  # 실제 DB·Chroma 대신 (단위 테스트)
    return TestClient(app)


@pytest.fixture()
def store(tmp_path: Path) -> ChromaVectorStore:
    return ChromaVectorStore(tmp_path / "chroma")


def index_services(factory: sessionmaker[Session], store: ChromaVectorStore) -> IndexServices:
    return IndexServices(factory, store, PointerCache(factory))


def activate(factory: sessionmaker[Session], store: ChromaVectorStore, key: str, *,
             with_collection: bool = True) -> int:  # fmt: skip
    with factory() as db:
        run_id = _active(db, key)
    if with_collection:
        store.create_collection(f"{key}_run{run_id}", {})
    return run_id


def test_all_enabled_sources_active_is_ok(
    session_factory: sessionmaker[Session], store: ChromaVectorStore
) -> None:
    v03 = activate(session_factory, store, V03)
    v1x = activate(session_factory, store, V1X)

    response = client_with(index_services(session_factory, store)).get("/internal/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "chroma": "loaded",
        "database": "ok",
        "sources": {
            V03: {"activeRun": True, "ingestRunId": v03},
            V1X: {"activeRun": True, "ingestRunId": v1x},
        },
    }


@pytest.mark.parametrize("with_collection", [False, None])
def test_missing_pointer_or_collection_is_degraded(
    session_factory: sessionmaker[Session], store: ChromaVectorStore, with_collection: Any
) -> None:
    activate(session_factory, store, V03)
    if with_collection is False:  # 포인터는 있는데 컬렉션이 없음 (스냅샷 미복원)
        activate(session_factory, store, V1X, with_collection=False)
    # None: v1.x 포인터 자체가 없음

    response = client_with(index_services(session_factory, store)).get("/internal/v1/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["sources"][V1X] == {"activeRun": False, "ingestRunId": None}
    assert body["sources"][V03]["activeRun"] is True


def test_disabled_sources_are_not_judged(
    session_factory: sessionmaker[Session], store: ChromaVectorStore
) -> None:
    activate(session_factory, store, V03)
    with session_factory() as db:
        source = db.scalar(select(Source).where(Source.source_key == V1X))
        assert source is not None
        source.enabled = False
        db.commit()

    response = client_with(index_services(session_factory, store)).get("/internal/v1/health")

    assert response.status_code == 200
    assert set(response.json()["sources"]) == {V03}


def test_database_failure_is_degraded(store: ChromaVectorStore) -> None:
    def broken_factory() -> Session:
        raise ConnectionError("db down")

    index = IndexServices(broken_factory, store, PointerCache(broken_factory))  # type: ignore[arg-type]

    response = client_with(index).get("/internal/v1/health")

    assert response.status_code == 503
    assert response.json() == {
        "status": "degraded", "chroma": "loaded", "database": "error", "sources": {}
    }  # fmt: skip


def test_unbuildable_services_are_degraded() -> None:
    response = client_with(None).get("/internal/v1/health")

    assert response.status_code == 503
    assert response.json()["chroma"] == "error"


def test_docs_exposed_outside_prod() -> None:
    client = client_with(None)

    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_docs_hidden_in_prod(
    session_factory: sessionmaker[Session], store: ChromaVectorStore
) -> None:
    activate(session_factory, store, V03)
    activate(session_factory, store, V1X)
    client = client_with(index_services(session_factory, store), profile="prod")

    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/internal/v1/health").status_code == 200  # 토큰 없이 호출

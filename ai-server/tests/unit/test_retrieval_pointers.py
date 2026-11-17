"""활성 인덱스 포인터 조회·캐시 — ADR-004, 정책서 §2.1 (30초 캐시 + reload 즉시 반영)."""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from src.domain.ingest_status import IngestStatus
from src.domain.tables import IndexPointer, IngestRun, Source
from src.retrieval.errors import IndexNotActiveError, SourceNotFoundError, SourceUnavailableError
from src.retrieval.pointers import (
    ActiveIndex,
    PointerCache,
    StaticPointers,
    load_active_index,
)

KEY = "langchain_v1x"
SHA = "a" * 40


def _active(session: Session, source_key: str = KEY, status: str = IngestStatus.ACTIVE) -> int:
    run = IngestRun(
        source_key=source_key,
        status=status,
        commit_sha=SHA,
        chunk_count=120,
        embedding_model="text-embedding-3-small",
        accept_drift=False,
        completed_at=datetime(2026, 11, 17, 3, 0, tzinfo=UTC),
    )
    session.add(run)
    session.flush()
    pointer = session.get(IndexPointer, source_key)
    if pointer is None:
        session.add(IndexPointer(source_key=source_key, active_run_id=run.id))
    else:
        pointer.active_run_id = run.id
    session.commit()
    return run.id


def test_load_active_index_returns_run_snapshot(session: Session) -> None:
    run_id = _active(session)

    index = load_active_index(session, KEY)

    assert index == ActiveIndex(
        source_key=KEY,
        version="v1.x",
        run_id=run_id,
        commit_sha=SHA,
        ingested_at=date(2026, 11, 17),
        chunk_count=120,
        embedding_model="text-embedding-3-small",
    )
    assert index.collection == f"{KEY}_run{run_id}"


def test_unknown_source_is_not_found(session: Session) -> None:
    with pytest.raises(SourceNotFoundError) as exc:
        load_active_index(session, "react_v18")
    assert exc.value.code == "SOURCE_NOT_FOUND" and exc.value.http_status == 404


def test_disabled_source_is_unavailable(session: Session) -> None:
    _active(session)
    source = session.scalar(select(Source).where(Source.source_key == KEY))
    assert source is not None
    source.enabled = False
    session.commit()

    with pytest.raises(SourceUnavailableError) as exc:
        load_active_index(session, KEY)
    assert exc.value.http_status == 409


def test_missing_pointer_is_index_not_active(session: Session) -> None:
    with pytest.raises(IndexNotActiveError) as exc:
        load_active_index(session, KEY)
    assert exc.value.code == "INDEX_NOT_ACTIVE" and exc.value.http_status == 503


def test_pointer_to_non_active_run_is_index_not_active(session: Session) -> None:
    _active(session, status=IngestStatus.SUPERSEDED)  # INV-01 위반 상태

    with pytest.raises(IndexNotActiveError):
        load_active_index(session, KEY)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_cache_serves_snapshot_for_30_seconds(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as db:
        first = _active(db)
    clock = Clock()
    cache = PointerCache(session_factory, clock=clock)
    assert cache.get(KEY).run_id == first

    with session_factory() as db:
        second = _active(db)  # 활성화로 포인터 교체
    clock.now += 29.9
    assert cache.get(KEY).run_id == first  # 아직 캐시
    clock.now += 0.2
    assert cache.get(KEY).run_id == second  # 30초 만료 후 재조회


def test_invalidate_reflects_new_pointer_immediately(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as db:
        _active(db)
        _active(db, "langchain_v03")
    cache = PointerCache(session_factory, clock=Clock())
    cache.get(KEY)
    v03 = cache.get("langchain_v03")

    with session_factory() as db:
        second = _active(db)
        _active(db, "langchain_v03")
    cache.invalidate(KEY)

    assert cache.get(KEY).run_id == second
    assert cache.get("langchain_v03") == v03  # 다른 소스는 그대로

    cache.invalidate()
    assert cache.get("langchain_v03") != v03


def test_failures_are_not_cached(session_factory: sessionmaker[Session]) -> None:
    cache = PointerCache(session_factory, clock=Clock())
    with pytest.raises(IndexNotActiveError):
        cache.get(KEY)

    with session_factory() as db:
        run_id = _active(db)

    assert cache.get(KEY).run_id == run_id  # 캐시 만료를 기다리지 않는다


def test_static_pointers_pin_indexes() -> None:
    index = ActiveIndex(KEY, "v1.x", 3, SHA, None, None, None)
    pointers = StaticPointers({KEY: index})

    assert pointers.get(KEY) is index
    with pytest.raises(IndexNotActiveError):
        pointers.get("langchain_v03")

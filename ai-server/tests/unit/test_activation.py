"""활성화·롤백·정리 — 포인터 일관성(INV-01)과 1세대 롤백·정리 (정책서 §4.5)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.ingest_status import IngestStatus
from src.domain.tables import IndexPointer, IngestRun
from src.ingest.activation import ActivationError, activate, purge_expired_failed, rollback
from src.ingest.store import collection_name

S = IngestStatus
KEY = "langchain_v1x"


class FakeStore:
    def __init__(self) -> None:
        self.names: set[str] = set()

    def has_collection(self, name: str) -> bool:
        return name in self.names

    def delete_collection(self, name: str) -> None:
        self.names.discard(name)

    def __getattr__(self, name: str) -> Any:  # 이 테스트에서 쓰지 않는 VectorStore 메서드
        raise AttributeError(name)


@pytest.fixture()
def store() -> FakeStore:
    return FakeStore()


def _ready(session: Session, store: FakeStore, source_key: str = KEY) -> int:
    run = IngestRun(source_key=source_key, status=S.READY, accept_drift=False)
    session.add(run)
    session.commit()
    store.names.add(collection_name(source_key, run.id))
    return run.id


def _statuses(session: Session) -> dict[int, str]:
    session.expire_all()
    return {r.id: r.status for r in session.scalars(select(IngestRun).order_by(IngestRun.id))}


def _assert_inv01(session: Session, source_key: str = KEY) -> int:
    """소스당 ACTIVE run은 정확히 1개이고 포인터가 그 run을 가리킨다."""
    session.expire_all()
    actives = [
        r.id
        for r in session.scalars(select(IngestRun))
        if r.status == S.ACTIVE and r.source_key == source_key
    ]
    pointer = session.get(IndexPointer, source_key)
    assert len(actives) == 1
    assert pointer is not None and pointer.active_run_id == actives[0]
    return actives[0]


def test_first_activation_inserts_pointer(session: Session, store: FakeStore) -> None:
    run_id = _ready(session, store)
    result = activate(session, store, run_id)  # type: ignore[arg-type]

    assert (result.active_run_id, result.superseded, result.purged) == (run_id, [], [])
    assert _assert_inv01(session) == run_id


def test_reactivation_supersedes_and_purges_older(session: Session, store: FakeStore) -> None:
    first, second, third = (_ready(session, store) for _ in range(3))
    activate(session, store, first)  # type: ignore[arg-type]
    activate(session, store, second)  # type: ignore[arg-type]
    assert _statuses(session) == {first: S.SUPERSEDED, second: S.ACTIVE, third: S.READY}

    result = activate(session, store, third)  # type: ignore[arg-type]
    assert result.superseded == [second] and result.purged == [first]
    assert _statuses(session) == {first: S.PURGED, second: S.SUPERSEDED, third: S.ACTIVE}
    assert collection_name(KEY, first) not in store.names  # 컬렉션 삭제, 레코드는 보존
    assert _assert_inv01(session) == third


def test_rollback_swaps_one_generation(session: Session, store: FakeStore) -> None:
    first, second = _ready(session, store), _ready(session, store)
    activate(session, store, first)  # type: ignore[arg-type]
    activate(session, store, second)  # type: ignore[arg-type]

    rollback(session, store, KEY)  # type: ignore[arg-type]
    assert _statuses(session) == {first: S.ACTIVE, second: S.SUPERSEDED}
    assert _assert_inv01(session) == first

    rollback(session, store, KEY)  # type: ignore[arg-type]  # 다시 되돌리면 원래대로
    assert _assert_inv01(session) == second


@pytest.mark.parametrize("status", [S.VALIDATING, S.FAILED, S.ACTIVE, S.SUPERSEDED])
def test_only_ready_can_be_activated(session: Session, store: FakeStore, status: S) -> None:
    run = IngestRun(source_key=KEY, status=status, accept_drift=False)
    session.add(run)
    session.commit()
    store.names.add(collection_name(KEY, run.id))
    with pytest.raises(ActivationError, match="READY"):
        activate(session, store, run.id)  # type: ignore[arg-type]
    assert session.get(IndexPointer, KEY) is None


def test_activation_requires_collection(session: Session, store: FakeStore) -> None:
    run_id = _ready(session, store)
    store.names.clear()
    with pytest.raises(ActivationError, match="컬렉션"):
        activate(session, store, run_id)  # type: ignore[arg-type]
    assert _statuses(session) == {run_id: S.READY}


def test_rollback_without_previous_fails(session: Session, store: FakeStore) -> None:
    with pytest.raises(ActivationError, match="ACTIVE"):
        rollback(session, store, KEY)  # type: ignore[arg-type]
    activate(session, store, _ready(session, store))  # type: ignore[arg-type]
    with pytest.raises(ActivationError, match="SUPERSEDED"):
        rollback(session, store, KEY)  # type: ignore[arg-type]


def test_sources_are_independent(session: Session, store: FakeStore) -> None:
    v1x, v03 = _ready(session, store), _ready(session, store, "langchain_v03")
    activate(session, store, v1x)  # type: ignore[arg-type]
    activate(session, store, v03)  # type: ignore[arg-type]
    assert _assert_inv01(session, KEY) == v1x
    assert _assert_inv01(session, "langchain_v03") == v03


def test_purge_expired_failed(session: Session, store: FakeStore) -> None:
    now = datetime(2026, 11, 17, 12, tzinfo=UTC)
    old = IngestRun(source_key=KEY, status=S.FAILED, accept_drift=False)
    recent = IngestRun(source_key=KEY, status=S.FAILED, accept_drift=False)
    session.add_all([old, recent])
    session.commit()
    old.updated_at = now - timedelta(hours=25)
    recent.updated_at = now - timedelta(hours=1)
    session.commit()
    store.names.update({collection_name(KEY, old.id), collection_name(KEY, recent.id)})

    assert purge_expired_failed(session, store, now=now) == [old.id]  # type: ignore[arg-type]
    assert _statuses(session) == {old.id: S.PURGED, recent.id: S.FAILED}
    assert store.names == {collection_name(KEY, recent.id)}

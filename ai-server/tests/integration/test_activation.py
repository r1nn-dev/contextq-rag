"""활성화 트랜잭션 — 실제 PostgreSQL(행 잠금·FK)에서 INV-01을 확인한다."""

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from src.ingest.activation import activate, rollback
from src.ingest.store import collection_name

pytestmark = pytest.mark.integration

_INSERT_READY = (
    "INSERT INTO ai.ingest_runs (source_key, status, accept_drift, created_at, updated_at)"
    " VALUES ('langchain_v1x', 'READY', false, now(), now()) RETURNING id"
)


class _Store:
    def __init__(self, names: set[str]) -> None:
        self.names = names

    def has_collection(self, name: str) -> bool:
        return name in self.names

    def delete_collection(self, name: str) -> None:
        self.names.discard(name)


def _ready_runs(engine: Engine, count: int) -> list[int]:
    with engine.begin() as conn:
        return [conn.execute(text(_INSERT_READY)).scalar_one() for _ in range(count)]


def _state(engine: Engine) -> tuple[list[tuple[int, str]], list[tuple[str, int]]]:
    with engine.connect() as conn:
        runs = conn.execute(text("SELECT id, status FROM ai.ingest_runs ORDER BY id")).all()
        pointers = conn.execute(
            text("SELECT source_key, active_run_id FROM ai.index_pointers")
        ).all()
    return [(r[0], r[1]) for r in runs], [(p[0], p[1]) for p in pointers]


def test_activate_and_rollback_keep_single_active(migrated: Engine) -> None:
    first, second, third = _ready_runs(migrated, 3)
    store = _Store({collection_name("langchain_v1x", i) for i in (first, second, third)})

    with Session(migrated) as session:
        activate(session, store, first)  # type: ignore[arg-type]
        activate(session, store, second)  # type: ignore[arg-type]
        activate(session, store, third)  # type: ignore[arg-type]
    runs, pointers = _state(migrated)
    assert runs == [(first, "PURGED"), (second, "SUPERSEDED"), (third, "ACTIVE")]
    assert pointers == [("langchain_v1x", third)]

    with Session(migrated) as session:
        rollback(session, store, "langchain_v1x")  # type: ignore[arg-type]
    runs, pointers = _state(migrated)
    assert runs == [(first, "PURGED"), (second, "ACTIVE"), (third, "SUPERSEDED")]
    assert pointers == [("langchain_v1x", second)]

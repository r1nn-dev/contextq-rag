"""스냅샷 복원 — 실제 PostgreSQL에서 명시 run id INSERT와 시퀀스 보정 확인 (db-design §3.11)."""

from pathlib import Path

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from src.domain.ingest_status import IngestStatus
from src.ingest.snapshot import export_snapshot, restore_snapshot
from tests.memory_store import MemoryVectorStore
from tests.unit.test_snapshot import seed_run
from tests.unit.test_snapshot_restore import deps

pytestmark = pytest.mark.integration


def test_restore_inserts_run_id_and_advances_sequence(migrated: Engine, tmp_path: Path) -> None:
    factory = sessionmaker(migrated)
    local = MemoryVectorStore()
    with factory() as session:  # '로컬'에서 run 2개를 만든 뒤 마지막 run을 내보내고 지운다
        seed_run(session, local)
        run = seed_run(session, local)
        path = export_snapshot(session, local, run.id, tmp_path).path
        run_id = run.id
        session.delete(run)
        session.commit()
    with migrated.begin() as conn:  # 운영 DB처럼 시퀀스를 처음으로 되돌린다
        conn.execute(text("SELECT setval(pg_get_serial_sequence('ai.ingest_runs', 'id'), 1)"))

    summary = restore_snapshot(factory, path, deps(MemoryVectorStore()))

    assert (summary.run_id, summary.status) == (run_id, IngestStatus.READY)
    with Session(migrated) as session:
        next_id = session.execute(
            text(
                "INSERT INTO ai.ingest_runs (source_key, status, accept_drift, created_at,"
                " updated_at) VALUES ('langchain_v1x', 'PENDING', false, now(), now())"
                " RETURNING id"
            )
        ).scalar_one()
        session.commit()
    assert next_id > run_id

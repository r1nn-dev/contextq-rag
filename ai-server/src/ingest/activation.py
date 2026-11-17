"""인덱스 활성화·롤백·정리 — 정책서 §4.5·§10.1, db-design §3.12, ADR-004·005.

- 활성화: 기존 ACTIVE → SUPERSEDED, 대상 READY → ACTIVE, 포인터 교체를 한 트랜잭션에서 한다(INV-01).
- 롤백: 현재 ACTIVE ↔ 직전 SUPERSEDED (1세대만).
- 정리: 새 SUPERSEDED가 생기면 그 이전 SUPERSEDED, 24시간 지난 FAILED → PURGED(컬렉션 삭제).
- 컬렉션 삭제는 DB 커밋 뒤에 한다. 삭제가 실패해도 포인터·상태는 이미 일관된 상태다.
- 서버 반영용 reload API(`POST /internal/v1/index/reload`)는 내부 API 작업에서 추가한다.
  그 전까지는 정책서 §4.5대로 포인터 캐시(30초) 만료로 반영된다.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.ingest_status import IngestStatus
from src.domain.tables import IndexPointer, IngestRun
from src.ingest.runs import now_utc, transition
from src.ingest.store import VectorStore, collection_name

FAILED_RETENTION = timedelta(hours=24)  # 정책서 §4.5 FAILED는 24시간 후 PURGED


class ActivationError(RuntimeError):
    """활성화·롤백 전제 조건 위반 — DB는 바뀌지 않는다."""


@dataclass
class ActivationResult:
    source_key: str
    active_run_id: int
    superseded: list[int] = field(default_factory=list)
    purged: list[int] = field(default_factory=list)


def _runs(session: Session, source_key: str, status: IngestStatus) -> list[IngestRun]:
    # 같은 소스의 동시 활성화·롤백을 직렬화한다 (db-design §5 비관적 잠금)
    query = (
        select(IngestRun)
        .where(IngestRun.source_key == source_key, IngestRun.status == status)
        .order_by(IngestRun.updated_at.desc(), IngestRun.id.desc())
        .with_for_update()
    )
    return list(session.scalars(query))


def _set_pointer(session: Session, source_key: str, run_id: int) -> None:
    pointer = session.get(IndexPointer, source_key, with_for_update=True)
    if pointer is None:  # 첫 활성화 — 포인터는 NOT NULL FK라 미리 만들 수 없다
        session.add(IndexPointer(source_key=source_key, active_run_id=run_id))
    else:
        pointer.active_run_id = run_id
        pointer.updated_at = now_utc()


def _delete_collections(store: VectorStore, runs: list[IngestRun]) -> None:
    for run in runs:
        store.delete_collection(collection_name(run.source_key, run.id))


def activate(session: Session, store: VectorStore, run_id: int) -> ActivationResult:
    """READY run을 ACTIVE로 올린다 (`make activate-index RUN=…`)."""
    target = session.get(IngestRun, run_id, with_for_update=True)
    if target is None:
        raise ActivationError(f"run {run_id}이(가) 없습니다")
    if target.status != IngestStatus.READY:
        raise ActivationError(
            f"READY run만 활성화할 수 있습니다: run {run_id}은(는) {target.status}"
        )
    if not store.has_collection(collection_name(target.source_key, target.id)):
        raise ActivationError(f"run {run_id}의 컬렉션이 없습니다 (스냅샷 복원 필요)")

    source_key = target.source_key
    older = _runs(session, source_key, IngestStatus.SUPERSEDED)
    current = _runs(session, source_key, IngestStatus.ACTIVE)
    for run in current:
        transition(session, run, IngestStatus.SUPERSEDED)
    transition(session, target, IngestStatus.ACTIVE)
    _set_pointer(session, source_key, target.id)
    # 새 SUPERSEDED가 생겼을 때만 그 이전 SUPERSEDED를 정리한다 (롤백 1세대 보존)
    purged = older if current else []
    for run in purged:
        transition(session, run, IngestStatus.PURGED)
    session.commit()

    _delete_collections(store, purged)
    return ActivationResult(source_key, target.id, [r.id for r in current], [r.id for r in purged])


def rollback(session: Session, store: VectorStore, source_key: str) -> ActivationResult:
    """직전 SUPERSEDED를 다시 ACTIVE로, 현재 ACTIVE는 SUPERSEDED로 (`make rollback-index`)."""
    current = _runs(session, source_key, IngestStatus.ACTIVE)
    previous = _runs(session, source_key, IngestStatus.SUPERSEDED)
    if not current:
        raise ActivationError(f"{source_key}에 ACTIVE run이 없습니다")
    if not previous:
        raise ActivationError(f"{source_key}에 되돌릴 SUPERSEDED run이 없습니다 (1세대만 보관)")
    target = previous[0]
    if not store.has_collection(collection_name(source_key, target.id)):
        raise ActivationError(f"run {target.id}의 컬렉션이 없습니다")

    for run in current:
        transition(session, run, IngestStatus.SUPERSEDED)
    transition(session, target, IngestStatus.ACTIVE)
    _set_pointer(session, source_key, target.id)
    session.commit()
    return ActivationResult(source_key, target.id, [r.id for r in current])


def purge_expired_failed(
    session: Session, store: VectorStore, *, now: datetime | None = None
) -> list[int]:
    """24시간 지난 FAILED run을 PURGED로 바꾸고 컬렉션을 지운다. run 레코드는 보존한다."""
    cutoff = (now or now_utc()) - FAILED_RETENTION
    expired = list(
        session.scalars(
            select(IngestRun)
            .where(IngestRun.status == IngestStatus.FAILED, IngestRun.updated_at < cutoff)
            .with_for_update()
        )
    )
    for run in expired:
        transition(session, run, IngestStatus.PURGED)
    session.commit()
    _delete_collections(store, expired)
    return [r.id for r in expired]

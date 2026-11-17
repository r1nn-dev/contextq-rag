"""수집 실행(ingest_runs) 생성·상태 전이 저장 계층.

- 모든 상태 변경은 `transition()`을 거치며 정책서 §10.1에 없는 전이는 `InvalidTransitionError`.
- 커밋은 호출자가 한다. 이 모듈은 `flush()`까지만 한다.
- 실패 처리(`fail`)는 해당 run만 바꾼다. 다른 run(기존 ACTIVE 포함)은 건드리지 않는다 (RAG-10).
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.ingest_status import IngestStatus, can_transition
from src.domain.tables import IngestRun, Source

# failure_reason은 TEXT지만 리포트 가독성을 위해 길이를 제한한다
MAX_FAILURE_REASON = 2000


class InvalidTransitionError(ValueError):
    """정책서 §10.1 표에 없는 상태 전이."""


class SourceNotFoundError(LookupError):
    """카탈로그(`ai.sources`)에 없는 source_key."""


def now_utc() -> datetime:
    return datetime.now(UTC)


def get_source(session: Session, source_key: str) -> Source:
    source = session.scalar(select(Source).where(Source.source_key == source_key))
    if source is None:
        raise SourceNotFoundError(f"카탈로그에 없는 source_key입니다: {source_key}")
    return source


def create_run(
    session: Session, source_key: str, *, accept_drift: bool = False, **params: Any
) -> IngestRun:
    """PENDING run을 발급하고 실행 파라미터(청킹 전략 등)를 기록한다 (정책서 §10.1)."""
    get_source(session, source_key)
    if not can_transition(None, IngestStatus.PENDING):  # pragma: no cover - 표 고정값
        raise InvalidTransitionError("None → PENDING")
    for name in params:
        if not hasattr(IngestRun, name):
            raise AttributeError(f"ingest_runs에 없는 컬럼입니다: {name}")
    run = IngestRun(
        source_key=source_key, status=IngestStatus.PENDING, accept_drift=accept_drift, **params
    )
    session.add(run)
    session.flush()
    return run


def transition(session: Session, run: IngestRun, target: IngestStatus, **fields: Any) -> IngestRun:
    """run 상태를 target으로 바꾸고 함께 기록할 컬럼 값을 넣는다."""
    current = IngestStatus(run.status)
    if not can_transition(current, target):
        raise InvalidTransitionError(f"run {run.id}: {current} → {target}")
    for name, value in fields.items():
        if not hasattr(IngestRun, name):
            raise AttributeError(f"ingest_runs에 없는 컬럼입니다: {name}")
        setattr(run, name, value)
    run.status = target
    run.updated_at = now_utc()
    session.flush()
    return run


def fail(session: Session, run: IngestRun, reason: str) -> IngestRun:
    """현재 단계를 failure_stage로 남기고 FAILED로 전이한다."""
    stage = IngestStatus(run.status)
    return transition(
        session,
        run,
        IngestStatus.FAILED,
        failure_stage=stage.value,
        failure_reason=reason[:MAX_FAILURE_REASON],
    )

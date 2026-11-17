"""수집 실행 저장 계층 — 생성·전이·실패 기록 (SQLite)."""

import pytest
from sqlalchemy.orm import Session

from src.domain.ingest_status import IngestStatus
from src.domain.tables import IngestRun
from src.ingest.runs import (
    InvalidTransitionError,
    SourceNotFoundError,
    create_run,
    fail,
    transition,
)

S = IngestStatus


def test_create_run_issues_pending_run(session: Session) -> None:
    run = create_run(session, "langchain_v1x", accept_drift=True)
    session.commit()

    assert run.id is not None
    assert run.status == S.PENDING
    assert run.accept_drift is True
    assert run.created_at is not None


def test_create_run_rejects_unknown_source(session: Session) -> None:
    with pytest.raises(SourceNotFoundError):
        create_run(session, "langgraph_v1")


def test_transition_records_fields(session: Session) -> None:
    run = create_run(session, "langchain_v03")
    sha = "a" * 40
    transition(session, run, S.COLLECTING, commit_sha=sha)

    assert run.status == S.COLLECTING
    assert run.commit_sha == sha


def test_transition_rejects_skipping_stages(session: Session) -> None:
    run = create_run(session, "langchain_v03")
    with pytest.raises(InvalidTransitionError):
        transition(session, run, S.EMBEDDING)
    assert run.status == S.PENDING


def test_transition_rejects_unknown_column(session: Session) -> None:
    run = create_run(session, "langchain_v03")
    with pytest.raises(AttributeError):
        transition(session, run, S.COLLECTING, no_such_column=1)


def test_fail_records_stage_and_reason(session: Session) -> None:
    run = create_run(session, "langchain_v03")
    transition(session, run, S.COLLECTING)
    fail(session, run, "x" * 5000)

    assert run.status == S.FAILED
    assert run.failure_stage == "COLLECTING"
    assert len(run.failure_reason or "") == 2000


def test_fail_does_not_touch_active_run(session: Session) -> None:
    active = IngestRun(source_key="langchain_v03", status=S.ACTIVE, accept_drift=False)
    session.add(active)
    run = create_run(session, "langchain_v03")
    transition(session, run, S.COLLECTING)
    fail(session, run, "checkout failed")
    session.commit()

    session.refresh(active)
    assert active.status == S.ACTIVE


def test_failed_run_cannot_resume(session: Session) -> None:
    run = create_run(session, "langchain_v03")
    fail(session, run, "boom")
    with pytest.raises(InvalidTransitionError):
        transition(session, run, S.COLLECTING)

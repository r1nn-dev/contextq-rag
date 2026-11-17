"""인덱스 빌드 파이프라인 — `make ingest SOURCE=…` (ADR-005, 정책서 §10.1).

현재 구현 범위: PENDING → COLLECTING(sparse checkout, commit_sha 기록).
PROCESSING 이후 단계는 후속 작업에서 이어 붙인다. 어느 단계든 실패하면 해당 run만
FAILED로 만들고 기존 ACTIVE run은 건드리지 않는다 (RAG-10).
"""

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from src.domain.ingest_status import IngestStatus
from src.ingest.collect import GITHUB, checkout_spec, sparse_checkout
from src.ingest.runs import create_run, fail, get_source, now_utc, transition


class IngestFailedError(RuntimeError):
    """파이프라인 단계 실패 — run은 이미 FAILED로 기록된 상태다."""

    def __init__(self, run_id: int, stage: str, reason: str) -> None:
        super().__init__(f"run {run_id} FAILED({stage}): {reason}")
        self.run_id = run_id
        self.stage = stage


@dataclass(frozen=True)
class IngestOptions:
    data_dir: Path
    accept_drift: bool = False
    remote_base: str = GITHUB


def run_ingest(
    session_factory: sessionmaker[Session], source_key: str, options: IngestOptions
) -> int:
    """새 run을 발급하고 현재 구현된 단계까지 진행한다. run id를 돌려준다."""
    with session_factory() as session:
        source = get_source(session, source_key)
        run = create_run(session, source_key, accept_drift=options.accept_drift)
        session.commit()
        run_id = run.id

        try:
            transition(session, run, IngestStatus.COLLECTING, started_at=now_utc())
            session.commit()

            result = sparse_checkout(
                checkout_spec(source),
                options.data_dir / "raw" / source_key,
                remote_base=options.remote_base,
            )
            run.commit_sha = result.commit_sha
            run.updated_at = now_utc()
            session.commit()
        except Exception as exc:
            session.rollback()
            stage = run.status
            fail(session, run, f"{type(exc).__name__}: {exc}")
            session.commit()
            raise IngestFailedError(run_id, stage, str(exc)) from exc

        return run_id

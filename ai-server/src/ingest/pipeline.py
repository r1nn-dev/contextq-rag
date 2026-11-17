"""인덱스 빌드 파이프라인 — `make ingest SOURCE=…` (ADR-005, 정책서 §10.1).

현재 구현 범위: PENDING → COLLECTING(sparse checkout, commit_sha 기록)
→ PROCESSING(Source Adapter 전처리, 누락 스니펫 리포트). 청킹 이후는 후속 작업에서 잇는다.
어느 단계든 실패하면 해당 run만 FAILED로 만들고 기존 ACTIVE run은 건드리지 않는다 (RAG-10).
"""

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from src.adapters.base import AdapterContext, create_adapter
from src.domain.documents import NormalizedDocument
from src.domain.ingest_status import IngestStatus
from src.domain.tables import IngestRun, Source
from src.ingest.collect import GITHUB, checkout_spec, sparse_checkout
from src.ingest.reports import report_dir, write_missing_snippets
from src.ingest.runs import create_run, fail, get_source, now_utc, transition


class IngestFailedError(RuntimeError):
    """파이프라인 단계 실패 — run은 이미 FAILED로 기록된 상태다."""

    def __init__(self, run_id: int, stage: str, reason: str) -> None:
        super().__init__(f"run {run_id} FAILED({stage}): {reason}")
        self.run_id = run_id
        self.stage = stage


@dataclass(frozen=True)
class IngestSummary:
    run_id: int
    status: str
    documents: int = 0
    sections: int = 0
    missing_snippets: int = 0


@dataclass(frozen=True)
class IngestOptions:
    data_dir: Path
    accept_drift: bool = False
    remote_base: str = GITHUB


def _process(
    session: Session, run: IngestRun, source: Source, root: Path, options: IngestOptions
) -> list[NormalizedDocument]:
    """PROCESSING — Adapter로 전처리하고 누락 스니펫을 리포트·run에 남긴다."""
    transition(session, run, IngestStatus.PROCESSING)
    session.commit()

    adapter = create_adapter(source.adapter_class, AdapterContext(doc_path=source.doc_path))
    documents = list(adapter.iter_documents(root))
    missing = adapter.report.missing_snippets
    write_missing_snippets(report_dir(options.data_dir, run.id), missing)
    run.missing_snippets_count = len(missing)
    run.updated_at = now_utc()
    session.commit()
    return documents


def run_ingest(
    session_factory: sessionmaker[Session], source_key: str, options: IngestOptions
) -> IngestSummary:
    """새 run을 발급하고 현재 구현된 단계까지 진행한다."""
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

            documents = _process(session, run, source, result.root, options)
        except Exception as exc:
            session.rollback()
            stage = run.status
            fail(session, run, f"{type(exc).__name__}: {exc}")
            session.commit()
            raise IngestFailedError(run_id, stage, str(exc)) from exc

        return IngestSummary(
            run_id=run_id,
            status=run.status,
            documents=len(documents),
            sections=sum(len(d.sections) for d in documents),
            missing_snippets=run.missing_snippets_count or 0,
        )

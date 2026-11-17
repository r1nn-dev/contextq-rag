"""인덱스 빌드 파이프라인 — `make ingest SOURCE=…` (ADR-005, 정책서 §10.1).

현재 구현 범위: PENDING(파라미터 기록) → COLLECTING(sparse checkout, commit_sha 기록)
→ PROCESSING(Source Adapter 전처리 → 청킹 → 메타데이터 조립, 리포트).
임베딩 이후는 후속 작업에서 잇는다.
어느 단계든 실패하면 해당 run만 FAILED로 만들고 기존 ACTIVE run은 건드리지 않는다 (RAG-10).
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from src.adapters.base import AdapterContext, create_adapter
from src.config.ingest_config import (
    Strategy,
    embedding_model_name,
    load_chunking_config,
    params_hash,
)
from src.domain.ingest_status import IngestStatus
from src.domain.tables import IngestRun, Source
from src.ingest.chunking import ChunkingError, make_chunker, splits_code_fence
from src.ingest.collect import GITHUB, checkout_spec, sparse_checkout
from src.ingest.metadata import PreparedChunk, RunContext, assemble
from src.ingest.reports import report_dir, write_json, write_missing_snippets
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
    chunks: int = 0
    missing_snippets: int = 0


@dataclass(frozen=True)
class IngestOptions:
    data_dir: Path
    accept_drift: bool = False
    strategy: Strategy | None = None  # None이면 configs/ingest.yaml 기본 전략
    remote_base: str = GITHUB


@dataclass
class ProcessResult:
    documents: int = 0
    sections: int = 0
    chunks: list[PreparedChunk] = field(default_factory=list)


def _run_params(strategy: Strategy) -> dict[str, Any]:
    """PENDING 시점에 기록하는 실행 파라미터 (정책서 §10.1 "파라미터 기록")."""
    params = load_chunking_config().params(strategy)
    return {
        "chunk_strategy": strategy,
        "chunk_params": params,
        "chunk_params_hash": params_hash(params),
        "embedding_model": embedding_model_name(),
    }


def _chunking_report(
    run: IngestRun, chunks: list[PreparedChunk], skipped: list[dict[str, str]]
) -> dict[str, Any]:
    sizes = [len(c.content) for c in chunks]
    tokens = [c.metadata["token_count"] for c in chunks]
    return {
        "run_id": run.id,
        "chunk_strategy": run.chunk_strategy,
        "chunk_params": run.chunk_params,
        "chunk_params_hash": run.chunk_params_hash,
        "chunks": len(chunks),
        "avg_chars": round(sum(sizes) / len(sizes), 1) if sizes else 0,
        "max_chars": max(sizes, default=0),
        "avg_tokens": round(sum(tokens) / len(tokens), 1) if tokens else 0,
        "chunks_with_code": sum(1 for c in chunks if c.metadata["has_code"]),
        # 전략 A·B 사후 검사 — 코드 펜스를 가른 청크 수 (E2 보고 항목)
        "code_fence_split_chunks": sum(1 for c in chunks if splits_code_fence(c.content)),
        "skipped_documents": skipped,
    }


def _process(
    session: Session, run: IngestRun, source: Source, root: Path, options: IngestOptions
) -> ProcessResult:
    """PROCESSING — Adapter 전처리, 청킹, 메타데이터 조립, 리포트 기록."""
    transition(session, run, IngestStatus.PROCESSING)
    session.commit()

    adapter = create_adapter(source.adapter_class, AdapterContext(doc_path=source.doc_path))
    documents = list(adapter.iter_documents(root))

    strategy: Strategy = run.chunk_strategy  # type: ignore[assignment]
    chunker = make_chunker(strategy, dict(run.chunk_params or {}))
    context = RunContext(
        source_key=source.source_key,
        framework=source.framework,
        version=source.version_label,
        ingest_run_id=run.id,
        commit_sha=run.commit_sha or "",
        repo=source.repo_url,
        chunk_strategy=strategy,
        chunk_params_hash=run.chunk_params_hash or "",
        embedding_model=run.embedding_model or "",
    )
    result = ProcessResult(documents=len(documents))
    skipped: list[dict[str, str]] = []
    for document in documents:
        result.sections += len(document.sections)
        try:
            result.chunks.extend(assemble(context, document, chunker.chunk(document)))
        except ChunkingError as exc:  # 해당 문서만 건너뛰고 리포트에 남긴다 (interfaces.md §5)
            skipped.append({"file_path": document.file_path, "reason": str(exc)})

    directory = report_dir(options.data_dir, run.id)
    write_missing_snippets(directory, adapter.report.missing_snippets)
    write_json(directory, "chunking.json", _chunking_report(run, result.chunks, skipped))
    run.missing_snippets_count = len(adapter.report.missing_snippets)
    run.updated_at = now_utc()
    session.commit()
    return result


def run_ingest(
    session_factory: sessionmaker[Session], source_key: str, options: IngestOptions
) -> IngestSummary:
    """새 run을 발급하고 현재 구현된 단계까지 진행한다."""
    strategy = options.strategy or load_chunking_config().default_strategy
    with session_factory() as session:
        source = get_source(session, source_key)
        run = create_run(
            session, source_key, accept_drift=options.accept_drift, **_run_params(strategy)
        )
        session.commit()
        run_id = run.id

        try:
            transition(session, run, IngestStatus.COLLECTING, started_at=now_utc())
            session.commit()

            checkout = sparse_checkout(
                checkout_spec(source),
                options.data_dir / "raw" / source_key,
                remote_base=options.remote_base,
            )
            run.commit_sha = checkout.commit_sha
            run.updated_at = now_utc()
            session.commit()

            processed = _process(session, run, source, checkout.root, options)
        except Exception as exc:
            session.rollback()
            stage = run.status
            fail(session, run, f"{type(exc).__name__}: {exc}")
            session.commit()
            raise IngestFailedError(run_id, stage, str(exc)) from exc

        return IngestSummary(
            run_id=run_id,
            status=run.status,
            documents=processed.documents,
            sections=processed.sections,
            chunks=len(processed.chunks),
            missing_snippets=run.missing_snippets_count or 0,
        )

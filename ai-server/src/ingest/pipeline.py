"""인덱스 빌드 파이프라인 — `make ingest SOURCE=…` (ADR-005, 정책서 §10.1).

현재 구현 범위: PENDING(파라미터 기록) → COLLECTING(sparse checkout, commit_sha 기록)
→ PROCESSING(Source Adapter 전처리 → 청킹 → 메타데이터 조립, 리포트)
→ EMBEDDING(임베딩 → run 전용 컬렉션 저장, 토큰·비용 기록)
→ VALIDATING(정책서 §4.4 게이트, 10분 제한) → READY. 활성화는 별도 명령(activation.py)이다.
어느 단계든 실패하면 해당 run만 FAILED로 만들고 기존 ACTIVE run은 건드리지 않는다 (RAG-10).
"""

import asyncio
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from src.adapters.base import AdapterContext, create_adapter
from src.config.ingest_config import (
    SmokeConfig,
    Strategy,
    embedding_model_name,
    load_chunking_config,
    load_embedding_config,
    params_hash,
)
from src.domain.ingest_status import IngestStatus
from src.domain.tables import IngestRun, Source
from src.ingest.chunking import ChunkingError, make_chunker, splits_code_fence
from src.ingest.collect import GITHUB, checkout_spec, sparse_checkout
from src.ingest.embedder import EmbeddingClient, EmbeddingError, embedding_cost_usd
from src.ingest.metadata import PreparedChunk, RunContext, assemble
from src.ingest.reports import report_dir, write_json, write_missing_snippets
from src.ingest.runs import create_run, fail, get_source, now_utc, transition
from src.ingest.store import VectorStore, collection_name
from src.ingest.validate import (
    VALIDATION_TIMEOUT_SECONDS,
    CheckResult,
    Deadline,
    ValidationTimeoutError,
    check_chunk_count,
    check_collection_metadata,
    check_records,
    check_smoke,
)


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
    validation_timeout_seconds: float = VALIDATION_TIMEOUT_SECONDS


class PermalinkCheck(Protocol):
    def check(self, permalinks: Iterable[str], deadline: Deadline) -> CheckResult: ...


@dataclass(frozen=True)
class IngestDependencies:
    """외부 자원 — 테스트에서는 가짜 임베더·임시 Chroma·가짜 permalink 검사기로 바꾼다."""

    embedder_factory: Callable[[], EmbeddingClient]
    store: VectorStore
    price_per_1m_tokens_usd: float
    permalink_checker: PermalinkCheck
    smoke: SmokeConfig
    smoke_tau: Callable[[str], float]  # source_key → 서비스 τ (configs/rag.yaml + TAU_* 덮어쓰기)


class ValidationFailedError(RuntimeError):
    """게이트 항목 중 하나 이상 실패 — run은 FAILED(VALIDATING), 기존 ACTIVE 유지 (RAG-10)."""


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


def _embed(
    session: Session,
    run: IngestRun,
    chunks: list[PreparedChunk],
    deps: IngestDependencies,
) -> None:
    """EMBEDDING — 임베딩 후 run 전용 컬렉션에 저장하고 토큰·비용을 기록한다 → VALIDATING."""
    transition(session, run, IngestStatus.EMBEDDING)
    session.commit()

    if not chunks:
        raise EmbeddingError("청크가 0건이라 임베딩할 수 없습니다")
    embedder = deps.embedder_factory()
    if embedder.model != run.embedding_model:  # INV-03: run에 기록한 모델로만 임베딩한다
        raise EmbeddingError(
            f"임베딩 모델 불일치: run {run.embedding_model}, 클라이언트 {embedder.model}"
        )
    vectors = asyncio.run(embedder.embed([c.content for c in chunks]))

    name = collection_name(run.source_key, run.id)
    deps.store.create_collection(
        name,
        {
            "source_key": run.source_key,
            "ingest_run_id": run.id,
            "commit_sha": run.commit_sha or "",
            "chunk_strategy": run.chunk_strategy or "",
            "chunk_params_hash": run.chunk_params_hash or "",
            "embedding_model": embedder.model,
            "embedding_dim": embedder.dimensions,
        },
    )
    deps.store.add(
        name,
        ids=[c.chunk_id for c in chunks],
        embeddings=vectors,
        documents=[c.content for c in chunks],
        metadatas=[dict(c.metadata) for c in chunks],
    )

    run.chunk_count = len(chunks)
    run.embedding_tokens = embedder.total_tokens
    run.embedding_cost_usd = embedding_cost_usd(embedder.total_tokens, deps.price_per_1m_tokens_usd)
    # EMBEDDING → VALIDATING: 컬렉션 저장 완료 (정책서 §10.1)
    transition(session, run, IngestStatus.VALIDATING)
    session.commit()


def _as_utc(value: datetime) -> datetime:
    # SQLite(단위 테스트)는 tz 정보를 버리므로 UTC로 간주한다
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _gate_checks(
    run: IngestRun, deps: IngestDependencies, deadline: Deadline, checks: list[CheckResult]
) -> None:
    """정책서 §4.4 게이트 항목을 순서대로 실행해 checks에 쌓는다."""
    name = collection_name(run.source_key, run.id)
    model, dim = run.embedding_model or "", load_embedding_config().dimensions
    store = deps.store

    checks.append(check_chunk_count(run.chunk_count or 0, run.prev_chunk_count, run.accept_drift))
    checks.append(
        check_collection_metadata(
            store.collection_metadata(name), expected_model=model, expected_dim=dim
        )
    )
    checks.extend(
        check_records(
            store.iter_records(name, include_embeddings=True),
            expected_model=model,
            expected_dim=dim,
            deadline=deadline,
        )
    )
    deadline.check()
    permalinks = (str(r["metadata"].get("permalink", "")) for r in store.iter_records(name))
    checks.append(deps.permalink_checker.check(permalinks, deadline))
    deadline.check()
    checks.append(
        check_smoke(
            store,
            name,
            deps.embedder_factory(),
            deps.smoke.sources.get(run.source_key, []),
            tau=deps.smoke_tau(run.source_key),
            top_k=deps.smoke.top_k,
        )
    )
    deadline.check()


def _validate(
    session: Session, run: IngestRun, deps: IngestDependencies, options: IngestOptions
) -> None:
    """VALIDATING — 게이트 전 항목 통과 시 READY, 아니면 리포트를 남기고 실패를 올린다."""
    started = now_utc()
    deadline = Deadline.after(options.validation_timeout_seconds)
    previous = session.scalar(
        select(IngestRun).where(
            IngestRun.source_key == run.source_key, IngestRun.status == IngestStatus.ACTIVE
        )
    )
    run.prev_chunk_count = previous.chunk_count if previous else None

    checks: list[CheckResult] = []
    timed_out = False
    try:
        _gate_checks(run, deps, deadline, checks)
    except ValidationTimeoutError:
        timed_out = True

    passed = not timed_out and all(c.passed for c in checks)
    run.validation_report = {
        "passed": passed,
        "timed_out": timed_out,
        "duration_ms": int((now_utc() - started).total_seconds() * 1000),
        "checks": [c.as_dict() for c in checks],
        "snapshot_restore": "해당 없음 — RESTORING 경로에서만 검사 (정책서 §4.4)",
    }
    run.updated_at = now_utc()
    session.commit()

    if timed_out:
        raise ValidationTimeoutError(
            f"VALIDATION_TIMEOUT: {options.validation_timeout_seconds:.0f}초 안에 끝나지 않음"
        )
    if not passed:
        failed = ", ".join(c.name for c in checks if not c.passed)
        raise ValidationFailedError(f"VALIDATION_FAILED: {failed}")

    completed = now_utc()
    duration = completed - _as_utc(run.started_at or completed)
    transition(
        session,
        run,
        IngestStatus.READY,
        completed_at=completed,
        ingest_duration_ms=int(duration.total_seconds() * 1000),
    )
    session.commit()


def run_ingest(
    session_factory: sessionmaker[Session],
    source_key: str,
    options: IngestOptions,
    deps: IngestDependencies,
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
            _embed(session, run, processed.chunks, deps)
            _validate(session, run, deps, options)
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

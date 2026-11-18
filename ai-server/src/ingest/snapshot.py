"""인덱스 스냅샷 내보내기·복원 — 정책서 §4.4·§4.5·§10.1, ADR-005.

스냅샷 `snapshot-{source_key}-run{id}.tar.gz`는 두 파일로 구성한다.
- `manifest.json`: run 정보·청크 수·레코드 checksum·컬렉션 메타데이터·검증 리포트
- `records.jsonl`: 컬렉션 레코드(id·document·metadata·embedding)를 한 줄에 하나씩 정규화 JSON으로

임베디드 Chroma는 모든 컬렉션이 저장 파일 하나를 공유하므로 디렉터리를 run 단위로 떼어 내지 않고
레코드를 내보낸다. checksum은 레코드별 sha256을 정렬해 다시 해시한 값이라 레코드 순서와 무관하다.
전체 레코드를 메모리에 정렬하지 않아도 내보내기·복원·복원 후 검증에서 같은 값을 계산할 수 있다.

복원은 manifest의 run id로 RESTORING → (checksum) → VALIDATING → READY로 진행한다.
활성화는 CLI가 이어서 `activation.activate`를 호출한다 (`--activate`).
"""

import hashlib
import json
import tarfile
import tempfile
from array import array
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from src.config.ingest_config import SmokeConfig
from src.domain.ingest_status import IngestStatus, can_transition
from src.domain.tables import IngestRun
from src.ingest.embedder import EmbeddingClient
from src.ingest.runs import SourceNotFoundError, fail, get_source, now_utc, transition
from src.ingest.store import VectorStore, collection_name
from src.ingest.validate import (
    MAX_EXAMPLES,
    VALIDATION_TIMEOUT_SECONDS,
    CheckResult,
    Deadline,
    ValidationTimeoutError,
    check_collection_metadata,
    check_records,
    check_smoke,
)

FORMAT_VERSION = 1
MANIFEST = "manifest.json"
RECORDS = "records.jsonl"
# 게이트를 통과했고 컬렉션이 남아 있는 상태만 내보낸다
EXPORTABLE = frozenset({IngestStatus.READY, IngestStatus.ACTIVE, IngestStatus.SUPERSEDED})


class SnapshotError(RuntimeError):
    """스냅샷을 만들거나 복원할 수 없음 — 이 오류에서는 DB를 바꾸지 않는다."""


@dataclass(frozen=True)
class SnapshotResult:
    path: Path
    checksum_path: Path
    manifest: dict[str, Any]


def snapshot_name(source_key: str, run_id: int) -> str:
    return f"snapshot-{source_key}-run{run_id}.tar.gz"


def _canonical(payload: dict[str, Any]) -> bytes:
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return (text + "\n").encode("utf-8")


def _content(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(record["id"]),
        "document": record.get("document") or "",
        "metadata": dict(record.get("metadata") or {}),
    }


def record_line(record: dict[str, Any]) -> bytes:
    """`records.jsonl` 한 줄 — 키 정렬·공백 없는 JSON (파일 checksum `records_sha256`의 단위)."""
    embedding = [float(v) for v in record.get("embedding") or []]
    return _canonical({**_content(record), "embedding": embedding})


def content_line(record: dict[str, Any]) -> bytes:
    """임베딩을 뺀 내용 — 복원 후 정확 비교용 `content_sha256`의 단위.

    Chroma 저장·조회 왕복에서 임베딩 float32 값이 마지막 자리(1 ulp)만큼 바뀔 수 있으므로
    임베딩은 checksum이 아니라 오차(`EMBEDDING_TOLERANCE`)로 비교한다 (정책서 §4.4).
    """
    return _canonical(_content(record))


class RecordsDigest:
    """레코드 줄들의 순서 무관 checksum과 개수."""

    def __init__(self) -> None:
        self._digests: list[str] = []

    def update(self, line: bytes) -> None:
        self._digests.append(hashlib.sha256(line).hexdigest())

    @property
    def count(self) -> int:
        return len(self._digests)

    def hexdigest(self) -> str:
        return hashlib.sha256("".join(sorted(self._digests)).encode("ascii")).hexdigest()


def digest_records(records: Iterable[dict[str, Any]]) -> RecordsDigest:
    digest = RecordsDigest()
    for record in records:
        digest.update(record_line(record))
    return digest


def digest_contents(records: Iterable[dict[str, Any]]) -> RecordsDigest:
    digest = RecordsDigest()
    for record in records:
        digest.update(content_line(record))
    return digest


def file_sha256(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as fp:
        for block in iter(lambda: fp.read(1 << 20), b""):
            sha.update(block)
    return sha.hexdigest()


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def build_manifest(
    run: IngestRun,
    collection_metadata: dict[str, Any],
    digest: RecordsDigest,
    content: RecordsDigest,
    exported_at: datetime,
) -> dict[str, Any]:
    """정책서 §4.5 manifest. `run`은 복원 시 ingest_runs 행을 다시 만드는 데 쓴다."""
    return {
        "format_version": FORMAT_VERSION,
        "source_key": run.source_key,
        "ingest_run_id": run.id,
        "collection": collection_name(run.source_key, run.id),
        "commit_sha": run.commit_sha,
        "chunk_strategy": run.chunk_strategy,
        "chunk_params": run.chunk_params,
        "chunk_params_hash": run.chunk_params_hash,
        "embedding_model": run.embedding_model,
        "embedding_dim": collection_metadata.get("embedding_dim"),
        "chunk_count": digest.count,
        "records_sha256": digest.hexdigest(),
        "content_sha256": content.hexdigest(),
        "collection_metadata": collection_metadata,
        "validation_report": run.validation_report,
        "run": {
            "missing_snippets_count": run.missing_snippets_count,
            "embedding_tokens": run.embedding_tokens,
            "embedding_cost_usd": (
                str(run.embedding_cost_usd) if run.embedding_cost_usd is not None else None
            ),
            "ingest_duration_ms": run.ingest_duration_ms,
            "prev_chunk_count": run.prev_chunk_count,
            "accept_drift": run.accept_drift,
            "started_at": _iso(run.started_at),
            "completed_at": _iso(run.completed_at),
        },
        "exported_at": exported_at.isoformat(),
    }


def export_snapshot(
    session: Session,
    store: VectorStore,
    run_id: int,
    out_dir: Path,
    *,
    now: datetime | None = None,
) -> SnapshotResult:
    """run 하나를 스냅샷으로 내보낸다 (`make snapshot-index RUN=…`). DB는 읽기만 한다."""
    run = session.get(IngestRun, run_id)
    if run is None:
        raise SnapshotError(f"run {run_id}이(가) 없습니다")
    if run.status not in EXPORTABLE:
        raise SnapshotError(
            f"READY·ACTIVE·SUPERSEDED run만 내보낼 수 있습니다: run {run_id}은(는) {run.status}"
        )
    name = collection_name(run.source_key, run.id)
    if not store.has_collection(name):
        raise SnapshotError(f"run {run_id}의 컬렉션이 없습니다: {name}")

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / snapshot_name(run.source_key, run.id)
    with tempfile.TemporaryDirectory(dir=out_dir) as tmp:
        records_path = Path(tmp) / RECORDS
        digest, content = RecordsDigest(), RecordsDigest()
        with records_path.open("wb") as fp:
            for record in store.iter_records(name, include_embeddings=True):
                line = record_line(record)
                digest.update(line)
                content.update(content_line(record))
                fp.write(line)
        if run.chunk_count is not None and digest.count != run.chunk_count:
            raise SnapshotError(
                f"컬렉션 레코드 수({digest.count})가 run 기록({run.chunk_count})과 다릅니다"
            )

        manifest = build_manifest(
            run, store.collection_metadata(name), digest, content, now or datetime.now(UTC)
        )
        manifest_path = Path(tmp) / MANIFEST
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        with tarfile.open(path, "w:gz") as tar:  # manifest를 먼저 넣어 복원 사전 확인을 빠르게
            tar.add(manifest_path, arcname=MANIFEST)
            tar.add(records_path, arcname=RECORDS)

    checksum_path = path.with_name(path.name + ".sha256")
    # `sha256sum -c` 형식 — S3 다운로드 후 전송 손상을 확인한다
    checksum_path.write_text(f"{file_sha256(path)}  {path.name}\n", encoding="utf-8")
    return SnapshotResult(path, checksum_path, manifest)


# --- 복원 (`make restore-index SNAPSHOT=…`, 모든 프로필) -----------------------------------------

RESTORE_BATCH = 500  # 컬렉션 적재 배치 — 운영 메모리(2GiB)에서 임베딩을 한꺼번에 올리지 않는다
EMBEDDING_TOLERANCE = 1e-6  # 복원 후 임베딩 허용 오차 (Chroma 왕복 1 ulp, 정책서 §4.4)


@dataclass(frozen=True)
class RestoreDependencies:
    """복원 게이트 외부 자원 — 테스트에서는 인메모리 저장소·가짜 임베더로 바꾼다."""

    store: VectorStore
    embedder_factory: Callable[[], EmbeddingClient]
    smoke: SmokeConfig
    smoke_tau: Callable[[str], float]
    embedding_model: str  # 현재 설정의 임베딩 모델 (INV-03)
    embedding_dim: int
    validation_timeout_seconds: float = VALIDATION_TIMEOUT_SECONDS


@dataclass(frozen=True)
class RestoreSummary:
    run_id: int
    source_key: str
    status: str
    chunk_count: int


def _read_manifest(tar: tarfile.TarFile) -> dict[str, Any]:
    names = tar.getnames()
    member = tar.extractfile(MANIFEST) if MANIFEST in names else None
    if member is None:
        raise SnapshotError(f"스냅샷에 {MANIFEST}이(가) 없습니다")
    manifest = json.load(member)
    if not isinstance(manifest, dict) or manifest.get("format_version") != FORMAT_VERSION:
        raise SnapshotError(f"지원하지 않는 스냅샷 형식입니다 (format_version {FORMAT_VERSION}만)")
    required = (
        "source_key", "ingest_run_id", "chunk_count", "records_sha256", "content_sha256",
        "embedding_model",
    )  # fmt: skip
    for key in required:
        if manifest.get(key) in (None, ""):
            raise SnapshotError(f"manifest에 {key}가 없습니다")
    if RECORDS not in names:
        raise SnapshotError(f"스냅샷에 {RECORDS}이(가) 없습니다")
    return manifest


def _iter_lines(tar: tarfile.TarFile) -> Iterator[bytes]:
    """records.jsonl을 디스크에 풀지 않고 줄 단위로 읽는다 (경로 조작 위험 없음)."""
    member = tar.extractfile(RECORDS)
    if member is None:  # pragma: no cover - _read_manifest에서 확인
        raise SnapshotError(f"스냅샷에 {RECORDS}이(가) 없습니다")
    for line in member:
        if line.strip():
            yield line if line.endswith(b"\n") else line + b"\n"


def _preflight(session: Session, manifest: dict[str, Any], deps: RestoreDependencies) -> None:
    """DB를 바꾸기 전에 거부할 조건 — 하나라도 어긋나면 run을 만들지 않는다."""
    source_key = str(manifest["source_key"])
    run_id = int(manifest["ingest_run_id"])
    try:
        get_source(session, source_key)
    except SourceNotFoundError as exc:
        raise SnapshotError(str(exc)) from exc
    if (
        manifest["embedding_model"] != deps.embedding_model
        or manifest.get("embedding_dim") != deps.embedding_dim
    ):
        raise SnapshotError(
            "EMBEDDING_MODEL_MISMATCH: 스냅샷 "
            f"{manifest['embedding_model']}({manifest.get('embedding_dim')}) ≠ 현재 설정 "
            f"{deps.embedding_model}({deps.embedding_dim})"
        )
    existing = session.get(IngestRun, run_id)
    if existing is not None:
        raise SnapshotError(
            f"run {run_id}이(가) 이미 있습니다({existing.status}). "
            "같은 run id는 다시 복원하지 않습니다"
        )
    name = collection_name(source_key, run_id)
    if deps.store.has_collection(name):
        raise SnapshotError(f"컬렉션이 이미 있습니다: {name}")


def _parse_time(value: Any) -> datetime | None:
    return datetime.fromisoformat(value) if isinstance(value, str) and value else None


def _sync_run_id_sequence(session: Session) -> None:
    """명시 id INSERT는 시퀀스를 올리지 않으므로 max(id)에 맞춘다 (로컬 수집의 PK 충돌 방지)."""
    if session.get_bind().dialect.name != "postgresql":
        return
    session.execute(
        text(
            "SELECT setval(pg_get_serial_sequence('ai.ingest_runs', 'id'), "
            "(SELECT max(id) FROM ai.ingest_runs))"
        )
    )


def _create_restoring_run(session: Session, manifest: dict[str, Any]) -> IngestRun:
    """manifest의 run id로 RESTORING run을 만든다 (`GENERATED BY DEFAULT`, db-design §3.11)."""
    if not can_transition(None, IngestStatus.RESTORING):  # pragma: no cover - 표 고정값
        raise SnapshotError("None → RESTORING 전이가 허용되지 않습니다")
    extra = manifest.get("run") or {}
    cost = extra.get("embedding_cost_usd")
    run = IngestRun(
        id=int(manifest["ingest_run_id"]),
        source_key=str(manifest["source_key"]),
        status=IngestStatus.RESTORING,
        commit_sha=manifest.get("commit_sha"),
        chunk_strategy=manifest.get("chunk_strategy"),
        chunk_params=manifest.get("chunk_params"),
        chunk_params_hash=manifest.get("chunk_params_hash"),
        embedding_model=manifest["embedding_model"],
        missing_snippets_count=extra.get("missing_snippets_count"),
        embedding_tokens=extra.get("embedding_tokens"),
        embedding_cost_usd=Decimal(cost) if cost is not None else None,
        accept_drift=bool(extra.get("accept_drift", False)),
        started_at=_parse_time(extra.get("started_at")),
    )
    session.add(run)
    session.flush()
    _sync_run_id_sequence(session)
    return run


def _load_collection(
    tar: tarfile.TarFile, manifest: dict[str, Any], store: VectorStore, name: str
) -> None:
    # 거리 함수(hnsw:space)까지 manifest 값 그대로 — Chroma 구현은 cosine으로 다시 고정한다
    store.create_collection(name, dict(manifest.get("collection_metadata") or {}))
    batch: list[dict[str, Any]] = []

    def flush() -> None:
        store.add(
            name,
            ids=[r["id"] for r in batch],
            embeddings=[r["embedding"] for r in batch],
            documents=[r["document"] for r in batch],
            metadatas=[r["metadata"] for r in batch],
        )
        batch.clear()

    for line in _iter_lines(tar):
        batch.append(json.loads(line))
        if len(batch) >= RESTORE_BATCH:
            flush()
    if batch:
        flush()


def _check_embeddings(
    tar: tarfile.TarFile, store: VectorStore, name: str, deadline: Deadline
) -> CheckResult:
    """복원된 임베딩이 스냅샷 값과 오차 범위 안인지 — 스냅샷 값은 float32 배열로 들고 있는다."""
    expected: dict[str, array[float]] = {}
    for line in _iter_lines(tar):
        record = json.loads(line)
        expected[str(record["id"])] = array("f", record["embedding"])
    max_diff, unexpected, mismatched = 0.0, 0, 0
    examples: list[str] = []
    for index, record in enumerate(store.iter_records(name, include_embeddings=True)):
        if index % 500 == 0:
            deadline.check()
        record_id = str(record["id"])
        want = expected.pop(record_id, None)
        got = record.get("embedding") or []
        if want is None:
            unexpected += 1
            continue
        diff = (
            max((abs(a - b) for a, b in zip(got, want, strict=True)), default=0.0)
            if len(got) == len(want)
            else float("inf")
        )
        max_diff = max(max_diff, diff)
        if diff > EMBEDDING_TOLERANCE:
            mismatched += 1
            if len(examples) < MAX_EXAMPLES:
                examples.append(record_id)
    missing = len(expected)
    return CheckResult(
        "snapshot_embeddings",
        missing == 0 and unexpected == 0 and mismatched == 0,
        {
            "tolerance": EMBEDDING_TOLERANCE,
            "max_abs_diff": max_diff,
            "missing": missing,
            "unexpected": unexpected,
            "mismatched": mismatched,
            "examples": examples,
        },
    )


def _restore_checks(
    tar: tarfile.TarFile,
    manifest: dict[str, Any],
    name: str,
    deps: RestoreDependencies,
    deadline: Deadline,
) -> list[CheckResult]:
    """정책서 §4.4 "스냅샷 복원 검증" — 청크 수·checksum·스모크가 manifest와 일치해야 한다."""
    store = deps.store
    expected_count = int(manifest["chunk_count"])
    count = store.count(name)
    checks = [
        CheckResult(
            "chunk_count",
            count == expected_count,
            {"chunk_count": count, "manifest_chunk_count": expected_count},
        ),
        check_collection_metadata(
            store.collection_metadata(name),
            expected_model=deps.embedding_model,
            expected_dim=deps.embedding_dim,
        ),
    ]
    checks.extend(
        check_records(
            store.iter_records(name, include_embeddings=True),
            expected_model=deps.embedding_model,
            expected_dim=deps.embedding_dim,
            deadline=deadline,
        )
    )
    deadline.check()
    restored = digest_contents(store.iter_records(name)).hexdigest()
    checks.append(
        CheckResult(
            "snapshot_content_checksum",
            restored == manifest["content_sha256"],
            {"restored_sha256": restored, "manifest_sha256": manifest["content_sha256"]},
        )
    )
    deadline.check()
    checks.append(_check_embeddings(tar, store, name, deadline))
    deadline.check()
    source_key = str(manifest["source_key"])
    checks.append(
        check_smoke(
            store,
            name,
            deps.embedder_factory(),
            deps.smoke.sources.get(source_key, []),
            tau=deps.smoke_tau(source_key),
            top_k=deps.smoke.top_k,
        )
    )
    deadline.check()
    return checks


def _validate_restored(
    session: Session,
    tar: tarfile.TarFile,
    run: IngestRun,
    manifest: dict[str, Any],
    snapshot: str,
    deps: RestoreDependencies,
) -> None:
    """VALIDATING — 복원 검증 게이트 통과 시 READY, 아니면 리포트를 남기고 실패를 올린다."""
    started = now_utc()
    deadline = Deadline.after(deps.validation_timeout_seconds)
    name = collection_name(run.source_key, run.id)
    checks: list[CheckResult] = []
    timed_out = False
    try:
        checks = _restore_checks(tar, manifest, name, deps, deadline)
    except ValidationTimeoutError:
        timed_out = True
    passed = not timed_out and all(c.passed for c in checks)
    run.chunk_count = deps.store.count(name)
    run.validation_report = {
        "passed": passed,
        "timed_out": timed_out,
        "duration_ms": int((now_utc() - started).total_seconds() * 1000),
        "checks": [c.as_dict() for c in checks],
        "snapshot_restore": {
            "snapshot": snapshot,
            "records_sha256": manifest["records_sha256"],
            "content_sha256": manifest["content_sha256"],
            "not_in_gate": {
                "chunk_drift": "복원은 manifest 청크 수와 일치 여부로 판정 (정책서 §4.4)",
                "permalink": "빌드 게이트에서 통과, 커밋 SHA 고정이라 결과 불변 (정책서 §4.4)",
            },
            "build_validation_report": manifest.get("validation_report"),
        },
    }
    run.updated_at = now_utc()
    session.commit()
    if timed_out:
        raise ValidationTimeoutError("VALIDATION_TIMEOUT: 복원 검증 제한 시간 초과")
    if not passed:
        failed = ", ".join(c.name for c in checks if not c.passed)
        raise SnapshotError(f"VALIDATION_FAILED: {failed}")
    transition(session, run, IngestStatus.READY, completed_at=now_utc())
    session.commit()


def restore_snapshot(
    session_factory: sessionmaker[Session], path: Path, deps: RestoreDependencies
) -> RestoreSummary:
    """스냅샷을 같은 run id로 복원한다: RESTORING → (checksum) → VALIDATING → READY.

    사전 확인에 걸리면 DB를 바꾸지 않는다. 그 뒤 실패는 해당 run만 FAILED로 남기고
    기존 ACTIVE는 건드리지 않는다 (RAG-10). FAILED run의 컬렉션은 24시간 뒤 정리된다.
    """
    if not path.is_file():
        raise SnapshotError(f"스냅샷 파일이 없습니다: {path}")
    with tarfile.open(path, "r:gz") as tar, session_factory() as session:
        manifest = _read_manifest(tar)
        _preflight(session, manifest, deps)
        run = _create_restoring_run(session, manifest)
        session.commit()
        run_id = run.id
        name = collection_name(run.source_key, run.id)
        try:
            # RESTORING: tar 레코드 checksum 확인 → 컬렉션 적재 (정책서 §10.1)
            streamed = RecordsDigest()
            for line in _iter_lines(tar):
                streamed.update(line)
            if streamed.hexdigest() != manifest["records_sha256"]:
                raise SnapshotError(
                    "SNAPSHOT_CHECKSUM_MISMATCH: records.jsonl이 manifest와 다릅니다 "
                    f"({streamed.hexdigest()[:12]}… ≠ {str(manifest['records_sha256'])[:12]}…)"
                )
            _load_collection(tar, manifest, deps.store, name)
            transition(session, run, IngestStatus.VALIDATING)
            session.commit()
            _validate_restored(session, tar, run, manifest, path.name, deps)
        except Exception as exc:
            session.rollback()
            stage = run.status
            fail(session, run, f"{type(exc).__name__}: {exc}")
            session.commit()
            raise SnapshotError(f"run {run_id} FAILED({stage}): {exc}") from exc
        return RestoreSummary(run_id, run.source_key, run.status, run.chunk_count or 0)

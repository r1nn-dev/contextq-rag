"""인덱스 스냅샷 내보내기 — 정책서 §4.5, ADR-005.

스냅샷 `snapshot-{source_key}-run{id}.tar.gz`는 두 파일로 구성한다.
- `manifest.json`: run 정보·청크 수·레코드 checksum·컬렉션 메타데이터·검증 리포트
- `records.jsonl`: 컬렉션 레코드(id·document·metadata·embedding)를 한 줄에 하나씩 정규화 JSON으로

임베디드 Chroma는 모든 컬렉션이 저장 파일 하나를 공유하므로 디렉터리를 run 단위로 떼어 내지 않고
레코드를 내보낸다. checksum은 레코드별 sha256을 정렬해 다시 해시한 값이라 레코드 순서와 무관하다.
전체 레코드를 메모리에 정렬하지 않아도 내보내기·복원·복원 후 검증에서 같은 값을 계산할 수 있다.
"""

import hashlib
import json
import tarfile
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from src.domain.ingest_status import IngestStatus
from src.domain.tables import IngestRun
from src.ingest.store import VectorStore, collection_name

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


def record_line(record: dict[str, Any]) -> bytes:
    """레코드 한 줄 — 키 정렬·공백 없는 JSON. 내보내기와 복원 후 검증이 같은 함수를 쓴다."""
    payload = {
        "id": str(record["id"]),
        "document": record.get("document") or "",
        "metadata": dict(record.get("metadata") or {}),
        "embedding": [float(v) for v in record.get("embedding") or []],
    }
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return (text + "\n").encode("utf-8")


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
        digest = RecordsDigest()
        with records_path.open("wb") as fp:
            for record in store.iter_records(name, include_embeddings=True):
                line = record_line(record)
                digest.update(line)
                fp.write(line)
        if run.chunk_count is not None and digest.count != run.chunk_count:
            raise SnapshotError(
                f"컬렉션 레코드 수({digest.count})가 run 기록({run.chunk_count})과 다릅니다"
            )

        manifest = build_manifest(
            run, store.collection_metadata(name), digest, now or datetime.now(UTC)
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

"""인덱스 스냅샷 내보내기 — 구성·결정성·거부 조건 (정책서 §4.5)."""

import hashlib
import json
import tarfile
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.orm import Session

from src.domain.ingest_status import IngestStatus
from src.domain.tables import IngestRun
from src.ingest.snapshot import (
    MANIFEST,
    RECORDS,
    SnapshotError,
    digest_records,
    export_snapshot,
    record_line,
    snapshot_name,
)
from src.ingest.store import collection_name
from tests.memory_store import MemoryVectorStore

KEY = "langchain_v1x"
MODEL = "text-embedding-3-small"
DIM = 4
SHA = "9d9747d0cf241e086c616a16d5ce230ad8f8f31d"


def make_records(count: int = 3) -> list[dict[str, Any]]:
    return [
        {
            "id": f"chunk{i:02d}",
            "document": f"본문 {i} — agents tools",
            "metadata": {
                "file_path": f"src/oss/doc{i}.mdx",
                "line_start": i,
                "has_code": i % 2 == 0,
            },
            "embedding": [0.25 * (i + 1), 0.5, -0.125, 1.0 / (i + 3)],
        }
        for i in range(count)
    ]


def seed_run(
    session: Session,
    store: MemoryVectorStore,
    *,
    status: IngestStatus = IngestStatus.READY,
    records: list[dict[str, Any]] | None = None,
    chunk_count: int | None = None,
) -> IngestRun:
    """게이트를 통과한 run과 그 컬렉션을 만든다 (빌드 파이프라인을 거치지 않는 테스트용)."""
    records = make_records() if records is None else records
    run = IngestRun(
        source_key=KEY,
        status=status,
        accept_drift=False,
        commit_sha=SHA,
        chunk_strategy="C",
        chunk_params={"max_tokens": 512},
        chunk_params_hash="a1b2c3d4",
        embedding_model=MODEL,
        chunk_count=len(records) if chunk_count is None else chunk_count,
        validation_report={"passed": True, "checks": []},
    )
    session.add(run)
    session.commit()
    name = collection_name(KEY, run.id)
    store.create_collection(
        name, {"source_key": KEY, "ingest_run_id": run.id, "embedding_model": MODEL,
               "embedding_dim": DIM, "hnsw:space": "cosine"},
    )  # fmt: skip
    store.add(
        name,
        ids=[r["id"] for r in records],
        embeddings=[r["embedding"] for r in records],
        documents=[r["document"] for r in records],
        metadatas=[r["metadata"] for r in records],
    )
    return run


def read_tar(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    with tarfile.open(path, "r:gz") as tar:
        assert tar.getnames() == [MANIFEST, RECORDS]
        manifest = json.load(tar.extractfile(MANIFEST))  # type: ignore[arg-type]
        lines = tar.extractfile(RECORDS).read().decode("utf-8").splitlines()  # type: ignore[union-attr]
    return manifest, [json.loads(line) for line in lines]


@pytest.fixture()
def store() -> MemoryVectorStore:
    return MemoryVectorStore()


def test_export_writes_manifest_records_and_checksum_file(
    session: Session, store: MemoryVectorStore, tmp_path: Path
) -> None:
    run = seed_run(session, store)
    result = export_snapshot(session, store, run.id, tmp_path)

    assert result.path == tmp_path / snapshot_name(KEY, run.id)
    assert result.path.name == f"snapshot-{KEY}-run{run.id}.tar.gz"
    manifest, records = read_tar(result.path)
    assert manifest == result.manifest
    assert {k: manifest[k] for k in ("format_version", "source_key", "ingest_run_id", "commit_sha",
                                      "chunk_strategy", "embedding_model", "embedding_dim",
                                      "chunk_count")} == {
        "format_version": 1, "source_key": KEY, "ingest_run_id": run.id, "commit_sha": SHA,
        "chunk_strategy": "C", "embedding_model": MODEL, "embedding_dim": DIM, "chunk_count": 3,
    }  # fmt: skip
    assert manifest["chunk_params"] == {"max_tokens": 512}
    assert manifest["validation_report"] == {"passed": True, "checks": []}
    assert sorted(r["id"] for r in records) == ["chunk00", "chunk01", "chunk02"]
    assert records[0]["embedding"] == [0.25, 0.5, -0.125, 1.0 / 3]
    assert manifest["records_sha256"] == digest_records(make_records()).hexdigest()

    digest, filename = result.checksum_path.read_text(encoding="utf-8").split()
    assert filename == result.path.name
    assert digest == hashlib.sha256(result.path.read_bytes()).hexdigest()


def test_records_checksum_is_order_independent_and_stable(
    session: Session, store: MemoryVectorStore, tmp_path: Path
) -> None:
    run = seed_run(session, store)
    first = export_snapshot(session, store, run.id, tmp_path / "a").manifest
    second = export_snapshot(session, store, run.id, tmp_path / "b").manifest

    assert first["records_sha256"] == second["records_sha256"]
    reordered = list(reversed(make_records()))
    assert digest_records(reordered).hexdigest() == first["records_sha256"]
    changed = make_records()
    changed[1]["document"] += "!"
    assert digest_records(changed).hexdigest() != first["records_sha256"]


def test_record_line_is_canonical() -> None:
    record = {"metadata": {"b": 1, "a": True}, "id": "x", "embedding": [1, 0.5], "document": "가"}
    assert (
        record_line(record)
        == (
            '{"document":"가","embedding":[1.0,0.5],"id":"x","metadata":{"a":true,"b":1}}\n'
        ).encode()
    )


@pytest.mark.parametrize("status", [IngestStatus.ACTIVE, IngestStatus.SUPERSEDED])
def test_active_and_superseded_runs_are_exportable(
    session: Session, store: MemoryVectorStore, tmp_path: Path, status: IngestStatus
) -> None:
    run = seed_run(session, store, status=status)
    assert export_snapshot(session, store, run.id, tmp_path).manifest["chunk_count"] == 3


@pytest.mark.parametrize(
    "status", [IngestStatus.VALIDATING, IngestStatus.FAILED, IngestStatus.PURGED]
)
def test_unvalidated_runs_are_rejected(
    session: Session, store: MemoryVectorStore, tmp_path: Path, status: IngestStatus
) -> None:
    run = seed_run(session, store, status=status)
    with pytest.raises(SnapshotError, match="READY·ACTIVE·SUPERSEDED"):
        export_snapshot(session, store, run.id, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_missing_run_or_collection_is_rejected(
    session: Session, store: MemoryVectorStore, tmp_path: Path
) -> None:
    with pytest.raises(SnapshotError, match="없습니다"):
        export_snapshot(session, store, 999, tmp_path)
    run = seed_run(session, store)
    store.delete_collection(collection_name(KEY, run.id))
    with pytest.raises(SnapshotError, match="컬렉션이 없습니다"):
        export_snapshot(session, store, run.id, tmp_path)


def test_record_count_mismatch_with_run_is_rejected(
    session: Session, store: MemoryVectorStore, tmp_path: Path
) -> None:
    run = seed_run(session, store, chunk_count=5)
    with pytest.raises(SnapshotError, match="run 기록"):
        export_snapshot(session, store, run.id, tmp_path)
    assert not (tmp_path / snapshot_name(KEY, run.id)).exists()

"""인덱스 스냅샷 복원 — 왕복·checksum·사전 확인·게이트 실패 (정책서 §4.4·§4.5·§10.1, RAG-10·11)."""

import io
import json
import tarfile
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from src.config.ingest_config import SmokeConfig, SmokeQuestion
from src.domain.ingest_status import IngestStatus
from src.domain.tables import IngestRun
from src.ingest import cli
from src.ingest.activation import activate
from src.ingest.snapshot import (
    MANIFEST,
    RECORDS,
    RestoreDependencies,
    SnapshotError,
    export_snapshot,
    restore_snapshot,
)
from src.ingest.store import ChromaVectorStore, collection_name
from tests.memory_store import MemoryVectorStore
from tests.unit.conftest import FakeEmbedder
from tests.unit.test_snapshot import DIM, KEY, MODEL, seed_run

S = IngestStatus


def smoke(expected: str = "src/oss/doc0.mdx") -> SmokeConfig:
    return SmokeConfig(
        top_k=3, sources={KEY: [SmokeQuestion(question="agents tools", expected_file=expected)]}
    )


def deps(store: MemoryVectorStore, **overrides: Any) -> RestoreDependencies:
    values: dict[str, Any] = {
        "store": store,
        "embedder_factory": lambda: FakeEmbedder(MODEL, DIM),
        "smoke": smoke(),
        "smoke_tau": lambda _key: 0.0,
        "embedding_model": MODEL,
        "embedding_dim": DIM,
    }
    values.update(overrides)
    return RestoreDependencies(**values)


def build_snapshot(
    session_factory: sessionmaker[Session], tmp_path: Path, status: S = S.ACTIVE
) -> tuple[Path, int]:
    """'로컬' DB·저장소에서 run을 만들어 내보낸 뒤, 그 run을 '운영' DB에서 지운다."""
    local_store = MemoryVectorStore()
    with session_factory() as session:
        run = seed_run(session, local_store, status=status)
        result = export_snapshot(session, local_store, run.id, tmp_path / "out")
        run_id = run.id
        session.delete(run)
        session.commit()
    return result.path, run_id


def rewrite(path: Path, *, manifest: dict[str, Any] | None = None, records: bytes | None = None
            ) -> Path:  # fmt: skip
    """스냅샷 tar의 manifest 또는 records를 바꿔 다시 묶는다 (변조·손상 시나리오)."""
    with tarfile.open(path, "r:gz") as tar:
        original_manifest = json.load(tar.extractfile(MANIFEST))  # type: ignore[arg-type]
        original_records = tar.extractfile(RECORDS).read()  # type: ignore[union-attr]
    out = path.with_name("tampered-" + path.name)
    with tarfile.open(out, "w:gz") as tar:
        for name, data in (
            (MANIFEST, json.dumps(manifest or original_manifest).encode()),
            (RECORDS, original_records if records is None else records),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return out


def runs(session_factory: sessionmaker[Session]) -> dict[int, tuple[str, str | None]]:
    with session_factory() as session:
        return {
            r.id: (r.status, r.failure_stage)
            for r in session.scalars(select(IngestRun).order_by(IngestRun.id))
        }


def test_round_trip_restores_same_run_and_collection(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    path, run_id = build_snapshot(session_factory, tmp_path)
    store = MemoryVectorStore()

    summary = restore_snapshot(session_factory, path, deps(store))

    assert (summary.run_id, summary.status, summary.chunk_count) == (run_id, S.READY, 3)
    with session_factory() as session:
        run = session.get(IngestRun, run_id)
        assert run is not None
        assert (run.commit_sha, run.chunk_strategy, run.embedding_model, run.chunk_count) == (
            "9d9747d0cf241e086c616a16d5ce230ad8f8f31d", "C", MODEL, 3,
        )  # fmt: skip
        report = run.validation_report or {}
        assert report["passed"] is True
        assert {c["name"] for c in report["checks"]} == {
            "chunk_count", "collection_metadata", "required_metadata", "preprocessing_residue",
            "embedding_model_dim", "snapshot_content_checksum", "snapshot_embeddings", "smoke",
        }  # fmt: skip
        assert report["snapshot_restore"]["build_validation_report"] == {
            "passed": True,
            "checks": [],
        }
    name = collection_name(KEY, run_id)
    assert store.collection_metadata(name)["embedding_dim"] == DIM
    restored = {r["id"]: r for r in store.iter_records(name, include_embeddings=True)}
    assert restored["chunk01"]["embedding"] == [0.5, 0.5, -0.125, 0.25]


def test_restored_run_can_be_activated(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    path, run_id = build_snapshot(session_factory, tmp_path)
    store = MemoryVectorStore()
    restore_snapshot(session_factory, path, deps(store))
    with session_factory() as session:
        assert activate(session, store, run_id).active_run_id == run_id
    assert runs(session_factory)[run_id] == (S.ACTIVE, None)


def test_tampered_records_fail_in_restoring_and_keep_active(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    store = MemoryVectorStore()
    with session_factory() as session:  # 운영에 이미 있는 ACTIVE run (RAG-10 확인용)
        active = seed_run(session, store, status=S.ACTIVE)
        active_id = active.id
    path, run_id = build_snapshot(session_factory, tmp_path)
    with tarfile.open(path, "r:gz") as tar:
        lines = tar.extractfile(RECORDS).read().splitlines(keepends=True)  # type: ignore[union-attr]
    tampered = rewrite(path, records=b"".join(lines[:-1]) + lines[-1].replace(b"agents", b"AGENT"))

    with pytest.raises(SnapshotError, match="SNAPSHOT_CHECKSUM_MISMATCH"):
        restore_snapshot(session_factory, tampered, deps(store))

    assert runs(session_factory) == {active_id: (S.ACTIVE, None), run_id: (S.FAILED, "RESTORING")}
    assert not store.has_collection(collection_name(KEY, run_id))


def test_smoke_failure_fails_in_validating(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    path, run_id = build_snapshot(session_factory, tmp_path)
    store = MemoryVectorStore()

    with pytest.raises(SnapshotError, match="VALIDATION_FAILED: smoke"):
        restore_snapshot(session_factory, path, deps(store, smoke=smoke("src/oss/missing.mdx")))

    assert runs(session_factory) == {run_id: (S.FAILED, "VALIDATING")}
    with session_factory() as session:
        report = session.get(IngestRun, run_id).validation_report  # type: ignore[union-attr]
    assert report is not None and report["passed"] is False


def test_manifest_count_mismatch_fails_gate(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    path, run_id = build_snapshot(session_factory, tmp_path)
    with tarfile.open(path, "r:gz") as tar:
        manifest = json.load(tar.extractfile(MANIFEST))  # type: ignore[arg-type]
    tampered = rewrite(path, manifest={**manifest, "chunk_count": 4})

    with pytest.raises(SnapshotError, match="chunk_count"):
        restore_snapshot(session_factory, tampered, deps(MemoryVectorStore()))
    assert runs(session_factory) == {run_id: (S.FAILED, "VALIDATING")}


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("existing_run", "이미 있습니다"),
        ("existing_collection", "컬렉션이 이미 있습니다"),
        ("unknown_source", "카탈로그에 없는"),
        ("model_mismatch", "EMBEDDING_MODEL_MISMATCH"),
        ("bad_format", "지원하지 않는 스냅샷 형식"),
    ],
)
def test_preflight_rejects_without_db_changes(
    session_factory: sessionmaker[Session], tmp_path: Path, case: str, message: str
) -> None:
    path, run_id = build_snapshot(session_factory, tmp_path)
    store = MemoryVectorStore()
    restore_deps = deps(store)
    with tarfile.open(path, "r:gz") as tar:
        manifest = json.load(tar.extractfile(MANIFEST))  # type: ignore[arg-type]
    if case == "existing_run":
        restore_snapshot(session_factory, path, deps(MemoryVectorStore()))
    elif case == "existing_collection":
        store.create_collection(collection_name(KEY, run_id), {})
    elif case == "unknown_source":
        path = rewrite(path, manifest={**manifest, "source_key": "langchain_v99"})
    elif case == "model_mismatch":
        restore_deps = deps(store, embedding_dim=1536)
    elif case == "bad_format":
        path = rewrite(path, manifest={**manifest, "format_version": 2})
    before = runs(session_factory)

    with pytest.raises(SnapshotError, match=message):
        restore_snapshot(session_factory, path, restore_deps)
    assert runs(session_factory) == before


def test_missing_file_is_rejected(session_factory: sessionmaker[Session], tmp_path: Path) -> None:
    with pytest.raises(SnapshotError, match="파일이 없습니다"):
        restore_snapshot(session_factory, tmp_path / "none.tar.gz", deps(MemoryVectorStore()))


def test_restore_command_is_registered_in_prod() -> None:
    settings = cli.Settings(_env_file=None, app_profile="prod")  # type: ignore[call-arg]
    argv = ["restore", "--snapshot", "s.tar.gz", "--activate"]
    args = cli.build_parser(settings).parse_args(argv)
    assert (args.command, args.snapshot, args.activate) == ("restore", Path("s.tar.gz"), True)


class DriftingStore(MemoryVectorStore):
    """저장할 때 임베딩을 `delta`만큼 바꾸는 대역 — Chroma 왕복 오차·손상 시나리오."""

    def __init__(self, delta: float) -> None:
        super().__init__()
        self.delta = delta

    def add(self, name: str, ids: Any, embeddings: Any, documents: Any, metadatas: Any) -> None:
        drifted = [[v + self.delta for v in e] for e in embeddings]
        super().add(name, ids, drifted, documents, metadatas)


@pytest.mark.parametrize(("delta", "passes"), [(6e-8, True), (1e-3, False)])
def test_embeddings_are_compared_with_tolerance(
    session_factory: sessionmaker[Session], tmp_path: Path, delta: float, passes: bool
) -> None:
    path, run_id = build_snapshot(session_factory, tmp_path)
    store = DriftingStore(delta)
    if passes:
        assert restore_snapshot(session_factory, path, deps(store)).status == S.READY
    else:
        with pytest.raises(SnapshotError, match="VALIDATION_FAILED: snapshot_embeddings"):
            restore_snapshot(session_factory, path, deps(store))
    with session_factory() as session:
        report = session.get(IngestRun, run_id).validation_report  # type: ignore[union-attr]
    embeddings = next(c for c in report["checks"] if c["name"] == "snapshot_embeddings")
    assert embeddings["passed"] is passes
    assert embeddings["max_abs_diff"] == pytest.approx(delta, rel=0.5)


def test_round_trip_into_real_chroma(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    """실제 Chroma는 왕복에서 float32 값을 1 ulp 바꾼다 — 그래도 복원 검증을 통과해야 한다."""
    path, run_id = build_snapshot(session_factory, tmp_path)
    store = ChromaVectorStore(tmp_path / "chroma")

    summary = restore_snapshot(session_factory, path, deps(store))  # type: ignore[arg-type]

    assert (summary.run_id, summary.status, summary.chunk_count) == (run_id, S.READY, 3)
    assert store.collection_metadata(collection_name(KEY, run_id))["hnsw:space"] == "cosine"

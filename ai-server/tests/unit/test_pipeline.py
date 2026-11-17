"""파이프라인 COLLECTING·PROCESSING — 성공 시 SHA·리포트, 실패 시 FAILED(단계)와 ACTIVE 유지."""

import csv
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.orm import Session, sessionmaker

from src.config.ingest_config import load_embedding_config
from src.domain.ingest_status import IngestStatus
from src.domain.tables import IngestRun, Source
from src.ingest.embedder import EmbeddingClient, OpenAIEmbeddingClient
from src.ingest.pipeline import (
    IngestDependencies,
    IngestFailedError,
    IngestOptions,
    run_ingest,
)
from src.ingest.store import ChromaVectorStore, collection_name
from tests.unit.conftest import FakeEmbedder

MINTLIFY_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "mintlify"


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture()
def remote_base(tmp_path: Path) -> str:
    """카탈로그의 langchain-ai/docs(main)를 Mintlify 픽스처 트리로 흉내 낸 로컬 저장소."""
    repo = tmp_path / "remote" / "langchain-ai" / "docs.git"
    shutil.copytree(MINTLIFY_FIXTURE / "src", repo / "src")
    _git(repo, "init", "--quiet", "--initial-branch", "main")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "init")
    return (tmp_path / "remote").as_uri()


def _options(tmp_path: Path, remote_base: str) -> IngestOptions:
    return IngestOptions(data_dir=tmp_path / "data", remote_base=remote_base)


@pytest.fixture()
def store(tmp_path: Path) -> ChromaVectorStore:
    return ChromaVectorStore(tmp_path / "chroma")


def _deps(store: ChromaVectorStore, embedder: EmbeddingClient | None = None) -> IngestDependencies:
    fake = embedder or FakeEmbedder()
    return IngestDependencies(
        embedder_factory=lambda: fake, store=store, price_per_1m_tokens_usd=0.02
    )


def test_ingest_reaches_validating(
    session_factory: sessionmaker[Session],
    tmp_path: Path,
    remote_base: str,
    store: ChromaVectorStore,
) -> None:
    summary = run_ingest(
        session_factory, "langchain_v1x", _options(tmp_path, remote_base), _deps(store)
    )

    assert summary.status == IngestStatus.VALIDATING
    assert (summary.documents, summary.sections, summary.missing_snippets) == (2, 3, 1)
    assert summary.chunks >= summary.sections
    with session_factory() as db:
        run = db.get_one(IngestRun, summary.run_id)
        assert run.commit_sha is not None and len(run.commit_sha) == 40
        assert run.started_at is not None
        assert run.missing_snippets_count == 1
        # PENDING 시점에 기록하는 실행 파라미터 (정책서 §10.1)
        assert run.chunk_strategy == "B"
        assert run.chunk_params == {
            "chunk_size": 1000,
            "chunk_overlap": 200,
            "separators": ["\n\n", "\n", " "],
        }
        assert run.chunk_params_hash is not None and len(run.chunk_params_hash) == 8
        assert run.embedding_model == "text-embedding-3-small"

    chunking = json.loads(
        (tmp_path / "data" / "reports" / f"run{summary.run_id}" / "chunking.json").read_text(
            encoding="utf-8"
        )
    )
    assert chunking["chunks"] == summary.chunks
    assert chunking["skipped_documents"] == []

    report = tmp_path / "data" / "reports" / f"run{summary.run_id}" / "missing_snippets.csv"
    with report.open(encoding="utf-8") as fp:
        rows = list(csv.reader(fp))
    assert rows == [
        ["file_path", "component", "import_path"],
        [
            "src/oss/langchain/agents.mdx",
            "AgentsMissingPy",
            "/snippets/code-samples/agents-missing-py.mdx",
        ],
    ]


def test_collect_failure_marks_run_failed_and_keeps_active(
    session_factory: sessionmaker[Session],
    tmp_path: Path,
    remote_base: str,
    store: ChromaVectorStore,
) -> None:
    with session_factory() as db:
        active = IngestRun(
            source_key="langchain_v03", status=IngestStatus.ACTIVE, accept_drift=False
        )
        db.add(active)
        db.commit()
        active_id = active.id

    # 카탈로그의 langchain-ai/langchain 저장소가 로컬 원격에 없으므로 clone이 실패한다
    with pytest.raises(IngestFailedError) as info:
        run_ingest(session_factory, "langchain_v03", _options(tmp_path, remote_base), _deps(store))

    with session_factory() as db:
        failed = db.get_one(IngestRun, info.value.run_id)
        assert failed.status == IngestStatus.FAILED
        assert failed.failure_stage == "COLLECTING"
        assert "CollectError" in (failed.failure_reason or "")
        assert db.get_one(IngestRun, active_id).status == IngestStatus.ACTIVE


def test_unregistered_adapter_fails_processing(
    session_factory: sessionmaker[Session],
    tmp_path: Path,
    remote_base: str,
    store: ChromaVectorStore,
) -> None:
    with session_factory() as db:
        db.add(
            Source(
                source_key="test_unknown",
                framework="test",
                version_label="v0",
                display_name="Test",
                repo_url="langchain-ai/docs",
                ref="main",
                doc_path="src/oss/",
                doc_format="MINTLIFY",
                adapter_class="NoSuchAdapter",
                enabled=True,
            )
        )
        db.commit()

    with pytest.raises(IngestFailedError) as info:
        run_ingest(session_factory, "test_unknown", _options(tmp_path, remote_base), _deps(store))

    with session_factory() as db:
        failed = db.get_one(IngestRun, info.value.run_id)
        assert failed.failure_stage == "PROCESSING"
        assert "AdapterNotRegisteredError" in (failed.failure_reason or "")


def test_strategy_option_is_recorded(
    session_factory: sessionmaker[Session],
    tmp_path: Path,
    remote_base: str,
    store: ChromaVectorStore,
) -> None:
    options = IngestOptions(data_dir=tmp_path / "data", strategy="C", remote_base=remote_base)
    summary = run_ingest(session_factory, "langchain_v1x", options, _deps(store))
    with session_factory() as db:
        assert db.get_one(IngestRun, summary.run_id).chunk_strategy == "C"


def test_embedding_stores_run_collection_and_cost(
    session_factory: sessionmaker[Session],
    tmp_path: Path,
    remote_base: str,
    store: ChromaVectorStore,
) -> None:
    summary = run_ingest(
        session_factory, "langchain_v1x", _options(tmp_path, remote_base), _deps(store)
    )
    name = collection_name("langchain_v1x", summary.run_id)

    with session_factory() as db:
        run = db.get_one(IngestRun, summary.run_id)
        assert run.chunk_count == summary.chunks == store.count(name)
        assert run.embedding_tokens is not None and run.embedding_tokens > 0
        assert run.embedding_cost_usd is not None
    meta = store.collection_metadata(name)
    assert meta["hnsw:space"] == "cosine"
    assert (meta["embedding_model"], meta["embedding_dim"]) == ("text-embedding-3-small", 1536)
    record = next(store.iter_records(name))
    assert record["metadata"]["ingest_run_id"] == summary.run_id
    assert record["metadata"]["source_key"] == "langchain_v1x"


@pytest.mark.parametrize(
    ("embedder_factory", "reason"),
    [
        (lambda: OpenAIEmbeddingClient("", load_embedding_config()), "OPENAI_API_KEY"),
        (lambda: FakeEmbedder(model="text-embedding-3-large"), "모델 불일치"),
    ],
)
def test_embedding_failure_marks_failed_without_collection(
    session_factory: sessionmaker[Session],
    tmp_path: Path,
    remote_base: str,
    store: ChromaVectorStore,
    embedder_factory: Any,
    reason: str,
) -> None:
    deps = IngestDependencies(
        embedder_factory=embedder_factory, store=store, price_per_1m_tokens_usd=0.02
    )
    with pytest.raises(IngestFailedError) as info:
        run_ingest(session_factory, "langchain_v1x", _options(tmp_path, remote_base), deps)

    with session_factory() as db:
        failed = db.get_one(IngestRun, info.value.run_id)
        assert failed.failure_stage == "EMBEDDING"
        assert reason in (failed.failure_reason or "")
    assert not store.has_collection(collection_name("langchain_v1x", info.value.run_id))

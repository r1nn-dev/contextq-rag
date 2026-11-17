"""파이프라인 COLLECTING·PROCESSING — 성공 시 SHA·리포트, 실패 시 FAILED(단계)와 ACTIVE 유지."""

import csv
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from src.domain.ingest_status import IngestStatus
from src.domain.tables import IngestRun, Source
from src.ingest.pipeline import IngestFailedError, IngestOptions, run_ingest

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


def test_processing_records_sha_and_missing_snippets(
    session_factory: sessionmaker[Session], tmp_path: Path, remote_base: str
) -> None:
    summary = run_ingest(session_factory, "langchain_v1x", _options(tmp_path, remote_base))

    assert summary.status == IngestStatus.PROCESSING
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
    session_factory: sessionmaker[Session], tmp_path: Path, remote_base: str
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
        run_ingest(session_factory, "langchain_v03", _options(tmp_path, remote_base))

    with session_factory() as db:
        failed = db.get_one(IngestRun, info.value.run_id)
        assert failed.status == IngestStatus.FAILED
        assert failed.failure_stage == "COLLECTING"
        assert "CollectError" in (failed.failure_reason or "")
        assert db.get_one(IngestRun, active_id).status == IngestStatus.ACTIVE


def test_unregistered_adapter_fails_processing(
    session_factory: sessionmaker[Session], tmp_path: Path, remote_base: str
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
        run_ingest(session_factory, "test_unknown", _options(tmp_path, remote_base))

    with session_factory() as db:
        failed = db.get_one(IngestRun, info.value.run_id)
        assert failed.failure_stage == "PROCESSING"
        assert "AdapterNotRegisteredError" in (failed.failure_reason or "")


def test_strategy_option_is_recorded(
    session_factory: sessionmaker[Session], tmp_path: Path, remote_base: str
) -> None:
    options = IngestOptions(data_dir=tmp_path / "data", strategy="C", remote_base=remote_base)
    summary = run_ingest(session_factory, "langchain_v1x", options)
    with session_factory() as db:
        assert db.get_one(IngestRun, summary.run_id).chunk_strategy == "C"

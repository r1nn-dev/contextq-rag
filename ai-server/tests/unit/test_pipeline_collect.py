"""파이프라인 COLLECTING 단계 — 성공 시 SHA 기록, 실패 시 FAILED(COLLECTING)와 기존 ACTIVE 유지."""

import subprocess
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from src.domain.ingest_status import IngestStatus
from src.domain.tables import IngestRun
from src.ingest.pipeline import IngestFailedError, IngestOptions, run_ingest


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture()
def remote_base(tmp_path: Path) -> str:
    """카탈로그의 langchain-ai/docs(main)를 흉내 낸 로컬 저장소."""
    repo = tmp_path / "remote" / "langchain-ai" / "docs.git"
    for rel in ["src/oss/a.mdx", "src/snippets/s.mdx"]:
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text("# a\n", encoding="utf-8")
    _git(repo, "init", "--quiet", "--initial-branch", "main")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "init")
    return (tmp_path / "remote").as_uri()


def test_collect_records_sha_and_stays_collecting(
    session_factory: sessionmaker[Session], tmp_path: Path, remote_base: str
) -> None:
    options = IngestOptions(data_dir=tmp_path / "data", remote_base=remote_base)
    run_id = run_ingest(session_factory, "langchain_v1x", options)

    with session_factory() as db:
        run = db.get_one(IngestRun, run_id)
        assert run.status == IngestStatus.COLLECTING
        assert run.commit_sha is not None and len(run.commit_sha) == 40
        assert run.started_at is not None
    assert (tmp_path / "data/raw/langchain_v1x/src/snippets/s.mdx").is_file()


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
    options = IngestOptions(data_dir=tmp_path / "data", remote_base=remote_base)
    with pytest.raises(IngestFailedError) as info:
        run_ingest(session_factory, "langchain_v03", options)

    with session_factory() as db:
        failed = db.get_one(IngestRun, info.value.run_id)
        assert failed.status == IngestStatus.FAILED
        assert failed.failure_stage == "COLLECTING"
        assert "CollectError" in (failed.failure_reason or "")
        assert db.get_one(IngestRun, active_id).status == IngestStatus.ACTIVE

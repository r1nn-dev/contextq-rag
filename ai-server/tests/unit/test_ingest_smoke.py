"""활성 인덱스 스모크 재실행 — 서비스와 같은 source_key별 τ (정책서 §4.4, 결정 규칙 §3-7)."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from src.config.ingest_config import SmokeConfig, SmokeQuestion
from src.domain.ingest_status import IngestStatus
from src.domain.tables import IndexPointer, IngestRun
from src.ingest.smoke import format_outcome, run_smoke
from src.ingest.store import ChromaVectorStore
from src.retrieval.errors import IndexNotActiveError
from tests.unit.test_validate import _KeywordEmbedder

KEY = "langchain_v1x"


def _activate(session: Session, store: ChromaVectorStore) -> int:
    run = IngestRun(source_key=KEY, status=IngestStatus.ACTIVE, accept_drift=False,
                    completed_at=datetime(2026, 11, 18, tzinfo=UTC))  # fmt: skip
    session.add(run)
    session.flush()
    session.add(IndexPointer(source_key=KEY, active_run_id=run.id))
    session.commit()
    store.create_collection(f"{KEY}_run{run.id}", {})
    store.add(
        f"{KEY}_run{run.id}",
        ids=["t"],
        embeddings=[[0.6, 0.8, 0.0]],  # "tools" 질문과 cosine 0.6
        documents=["tools"],
        metadatas=[{"file_path": "tools.mdx"}],
    )
    return run.id


SMOKE = SmokeConfig(
    top_k=1, sources={KEY: [SmokeQuestion(question="tools", expected_file="tools.mdx")]}
)


@pytest.mark.parametrize(("tau", "passed"), [(0.34, True), (0.61, False)])
def test_smoke_uses_source_tau_on_active_run(
    session: Session, tmp_path: Path, tau: float, passed: bool
) -> None:
    store = ChromaVectorStore(tmp_path / "chroma")
    run_id = _activate(session, store)
    seen: list[str] = []

    def tau_for(source_key: str) -> float:
        seen.append(source_key)
        return tau

    [outcome] = run_smoke(session, store, _KeywordEmbedder(), SMOKE, tau_for, [KEY])

    assert seen == [KEY]
    assert (outcome.run_id, outcome.tau, outcome.result.passed) == (run_id, tau, passed)
    assert f"run {run_id} τ={tau}" in format_outcome(outcome)


def test_smoke_without_active_index_raises(session: Session, tmp_path: Path) -> None:
    with pytest.raises(IndexNotActiveError):
        run_smoke(session, ChromaVectorStore(tmp_path / "c"), _KeywordEmbedder(), SMOKE,
                  lambda _k: 0.3, [KEY])  # fmt: skip

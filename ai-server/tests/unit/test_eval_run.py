"""검색 평가 러너 — 행 평가·요약·출력·조건 구성·CLI (evaluation.md §3·§4)."""

import csv
import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from src.domain.retrieval import RetrievedChunk, Retriever
from src.eval.questions import Gold, GoldSection, Metadata, OosQuestion, RetQuestion
from src.eval.run import (
    E1Inputs,
    RetrieverUnavailableError,
    e1_searchers,
    evaluate,
    main,
    summarize,
    unavailable_service_retriever,
    write_results,
)
from src.ingest.store import ChromaVectorStore

V03, V1X = "langchain_v03", "langchain_v1x"
META = Metadata(created_by="t", created_at="2026-11-17T00:00:00Z")


def _chunk(source_key: str, file_path: str, heading: str, sim: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=f"{source_key}:{file_path}:{heading}",
        content="",
        permalink="",
        source_key=source_key,
        file_path=file_path,
        heading_path=heading,
        token_count=50,
        site_url="",
        similarity=sim,
    )


class FakeRetriever:
    """질의·소스별 고정 결과 — 호출 기록을 남긴다."""

    def __init__(self, results: dict[tuple[str, str], list[RetrievedChunk]]) -> None:
        self.results = results
        self.calls: list[tuple[str, str, int]] = []

    def retrieve(self, query: str, source_key: str, top_k: int = 5) -> list[RetrievedChunk]:
        self.calls.append((query, source_key, top_k))
        return self.results.get((query, source_key), [])[:top_k]


RET = RetQuestion(
    question_id="RET-001",
    question_set="Q-ret",
    title="t",
    type="API_USAGE",
    difficulty="EASY",
    target_version="v1.x",
    query="툴 정의",
    gold=Gold(sections=[GoldSection(file_path="tools.mdx", heading_path="Tools > Create tools")]),
    metadata=META,
)
OOS = OosQuestion.model_validate(
    {
        "question_id": "OOS-001",
        "question_set": "Q-oos",
        "title": "t",
        "type": "OUT_OF_SCOPE",
        "difficulty": "EASY",
        "query": "Django",
        "expected_behavior": {"no_context": True, "reason": "r"},
        "metadata": META.model_dump(),
    }
)
RESULTS = {
    ("툴 정의", V1X): [
        _chunk(V03, "custom_tools.ipynb", "How to create tools", 0.8),
        _chunk(V1X, "tools.mdx", "Tools > Create tools > Basic", 0.7),
        _chunk(V1X, "agents.mdx", "Agents", 0.6),
    ],
    ("Django", V03): [_chunk(V03, "a.md", "A", 0.2)],
    ("Django", V1X): [_chunk(V1X, "b.md", "B", 0.3)],
}


def test_evaluate_searches_once_per_question_version_and_cuts_by_k() -> None:
    retriever = FakeRetriever(RESULTS)

    rows = evaluate(retriever, [RET], [OOS], experiment_id="e1", condition="E1-N", ks=(1, 2))

    assert retriever.calls == [("툴 정의", V1X, 2), ("Django", V03, 2), ("Django", V1X, 2)]
    ret_rows = [r for r in rows if r["question_set"] == "Q-ret"]
    assert [(r["top_k"], r["hit_at_k"], r["rr_at_k"]) for r in ret_rows] == [
        (1, 0, 0.0),
        (2, 1, 0.5),
    ]
    assert ret_rows[1]["contamination_at_k"] == 0.5
    assert ret_rows[1]["precision_at_k"] == 0.5
    assert ret_rows[1]["version"] == "v1.x"
    assert [c["is_gold"] for c in ret_rows[1]["chunks_returned"]] == [False, True]
    oos_rows = [r for r in rows if r["question_set"] == "Q-oos"]
    assert {r["version"] for r in oos_rows} == {"v0.3", "v1.x"}
    assert all(r["hit_at_k"] is None and r["tau"] is None for r in oos_rows)
    assert oos_rows[0]["max_score"] == 0.2


def test_summarize_groups_by_version_and_all() -> None:
    rows = evaluate(
        FakeRetriever(RESULTS), [RET], [OOS], experiment_id="e1", condition="E1-N", ks=(2,)
    )

    summary = {(s["question_set"], s["version"]): s for s in summarize(rows)}

    assert summary[("Q-ret", "v1.x")]["hit_at_k"] == 1.0
    assert summary[("Q-oos", "all")]["n"] == 2
    assert summary[("Q-oos", "all")]["hit_at_k"] is None
    assert summary[("Q-oos", "all")]["max_score_mean"] == pytest.approx(0.25)


def test_write_results_creates_jsonl_csv_and_env(tmp_path: Path) -> None:
    rows = evaluate(
        FakeRetriever(RESULTS), [RET], [OOS], experiment_id="e1", condition="E1-F", ks=(2,)
    )

    rows_path, summary_path = write_results(tmp_path, "E1", rows, {"experiment": "E1"})

    assert rows_path == tmp_path / "E1" / "e1_results.jsonl"
    lines = rows_path.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0])["condition"] == "E1-F"
    with summary_path.open(encoding="utf-8") as f:
        table = list(csv.DictReader(f))
    assert {row["version"] for row in table} == {"v0.3", "v1.x", "all"}
    assert (tmp_path / "E1" / "env.txt").read_text(encoding="utf-8") == "experiment: E1\n"


def test_e1_searchers_builds_n_and_f_and_uses_service_for_c(tmp_path: Path) -> None:
    store = ChromaVectorStore(tmp_path / "chroma")
    for key in (V03, V1X):
        store.create_collection(f"{key}_run1", {})
        store.add(
            f"{key}_run1",
            ids=[key],
            embeddings=[[1.0, 0.0]],
            documents=[key],
            metadatas=[{"source_key": key, "file_path": "f", "heading_path": "h"}],
        )
    service = FakeRetriever({})
    inputs = E1Inputs(store, {V03: 1, V1X: 1}, {"q": [1.0, 0.0]}, lambda: service)

    searchers: dict[str, Retriever] = e1_searchers(inputs, ["N", "F", "C"])

    assert set(searchers) == {"E1-N", "E1-F", "E1-C"}
    assert searchers["E1-C"] is service
    assert len(searchers["E1-N"].retrieve("q", V1X, 5)) == 2
    assert [c["source_key"] for c in searchers["E1-F"].retrieve("q", V1X, 5)] == [V1X]


def test_service_retriever_is_unavailable_until_connected() -> None:
    with pytest.raises(RetrieverUnavailableError, match="R-4-1"):
        unavailable_service_retriever()


def test_cli_check_reports_repository_question_sets(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--check"]) == 0
    assert "Q-ret" in capsys.readouterr().out


@pytest.mark.parametrize("argv", [["--exp", "E1"], ["--exp", "E2", "--conditions", "N"]])
def test_cli_exits_2_when_service_retriever_is_needed(
    argv: Sequence[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(argv) == 2
    assert "R-4-1" in capsys.readouterr().err


def test_cli_rejects_non_positive_k() -> None:
    assert main(["--exp", "E1", "--conditions", "N", "--k", "0"]) == 2

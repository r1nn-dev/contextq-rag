"""E2 — 전략별 run 선택·코드 블록 보존율·결정 규칙(decision_rules.md §1·§2)·결정 기록."""

from typing import Any

import pytest
from sqlalchemy.orm import Session

from src.domain.ingest_status import IngestStatus as S
from src.domain.tables import IngestRun
from src.eval.e2 import (
    Decision,
    FenceStats,
    StrategyRunsMissingError,
    StrategyScore,
    choose_k,
    choose_strategy,
    decide,
    fence_stats,
    strategy_indexes,
)
from src.eval.run import decision_markdown, main, strategy_scores
from src.retrieval.pointers import ActiveIndex

V03, V1X = "langchain_v03", "langchain_v1x"


def score(strategy: str, h3: float, h5: float, h8: float, mrr5: float, tokens: float = 200.0
          ) -> StrategyScore:  # fmt: skip
    return StrategyScore(strategy, {3: h3, 5: h5, 8: h8}, mrr5, tokens)


# --- 결정 규칙 §1 ------------------------------------------------------------


def test_hit5_gap_of_3pp_or_more_picks_the_leader() -> None:
    strategy, reasons = choose_strategy(
        [
            score("A", 0.5, 0.60, 0.7, 0.5),
            score("B", 0.5, 0.65, 0.7, 0.4),
            score("C", 0.5, 0.70, 0.7, 0.3),
        ]
    )

    assert strategy == "C"
    assert "차이 ≥ 3%p" in reasons[-1]


def test_hit5_gap_below_3pp_compares_mrr5_of_the_top_two_only() -> None:
    strategy, _ = choose_strategy(
        [
            score("A", 0.5, 0.675, 0.7, 0.30),
            score("B", 0.5, 0.65, 0.7, 0.45),
            score("C", 0.5, 0.64, 0.7, 0.90),
        ]
    )

    assert strategy == "B"  # C는 3위라 MRR이 높아도 비교 대상이 아니다


def test_equal_mrr5_picks_fewer_context_tokens() -> None:
    strategy, reasons = choose_strategy(
        [score("A", 0.5, 0.65, 0.7, 0.40001, 300.0), score("B", 0.5, 0.65, 0.7, 0.40004, 250.0)]
    )  # fmt: skip

    assert strategy == "B"  # 소수 넷째 자리까지 같으면 동률
    assert "평균 컨텍스트 토큰" in reasons[-1]


# --- 결정 규칙 §2 ------------------------------------------------------------


@pytest.mark.parametrize(
    ("h3", "h5", "h8", "k"),
    [
        (0.60, 0.615, 0.70, 3),
        (0.60, 0.65, 0.665, 5),
        (0.60, 0.65, 0.70, 8),
        (0.60, 0.62, 0.70, 8),
    ],  # 마지막: 정확히 2%p는 미만이 아님
)
def test_k_is_the_smallest_with_gain_below_2pp(h3: float, h5: float, h8: float, k: int) -> None:
    assert choose_k(score("B", h3, h5, h8, 0.4))[0] == k


def test_decide_needs_two_strategies() -> None:
    with pytest.raises(ValueError):
        decide([score("B", 0.5, 0.6, 0.7, 0.4)])


# --- 코드 블록 보존율 ---------------------------------------------------------


def test_fence_stats_counts_complete_and_split_fences() -> None:
    stats = fence_stats(["```py\nx\n```", "앞 ```py\na", "b\n``` 뒤", "코드 없음"])

    assert stats == FenceStats(complete=1, split_chunks=2)
    assert stats.preservation == 0.5
    assert fence_stats(["텍스트"]).preservation is None


# --- 전략별 run 선택 ----------------------------------------------------------


def _run(session: Session, source_key: str, strategy: str, status: S, sha: str = "a" * 40
         ) -> IngestRun:  # fmt: skip
    run = IngestRun(source_key=source_key, status=status, accept_drift=True,
                    chunk_strategy=strategy, chunk_count=10, commit_sha=sha)  # fmt: skip
    session.add(run)
    session.flush()
    return run


def test_strategy_indexes_picks_the_latest_searchable_run(session: Session) -> None:
    _run(session, V03, "B", S.ACTIVE)
    latest = _run(session, V03, "B", S.READY)
    _run(session, V1X, "B", S.SUPERSEDED)
    newest = _run(session, V1X, "B", S.READY)
    _run(session, V1X, "B", S.FAILED)

    found = strategy_indexes(session, [V03, V1X], ["B"])

    assert found["B"][V03].run_id == latest.id
    assert found["B"][V1X].run_id == newest.id
    assert found["B"][V1X].version == "v1.x"


def test_strategy_runs_of_one_source_must_share_the_commit(session: Session) -> None:
    _run(session, V1X, "B", S.ACTIVE, sha="b" * 40)
    _run(session, V1X, "C", S.READY, sha="c" * 40)

    with pytest.raises(StrategyRunsMissingError, match="커밋이 다릅니다"):
        strategy_indexes(session, [V1X], ["B", "C"])


def test_strategy_indexes_lists_missing_combinations(session: Session) -> None:
    _run(session, V03, "A", S.PURGED)

    with pytest.raises(StrategyRunsMissingError, match="langchain_v03/A"):
        strategy_indexes(session, [V03], ["A"])


def test_cli_exits_2_when_strategy_runs_are_missing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def missing(*_: Any) -> Any:
        raise StrategyRunsMissingError("검색할 수 있는 전략별 run이 없습니다: ['langchain_v03/A']")

    monkeypatch.setattr("src.eval.run.run_e2", missing)

    assert main(["--exp", "E2"]) == 2
    assert "langchain_v03/A" in capsys.readouterr().err


# --- 점수 집계와 결정 기록 ------------------------------------------------------


def _row(strategy: str, qid: str, version: str, qtype: str, k: int, hit: int, rr: float
         ) -> dict[str, Any]:  # fmt: skip
    chunks = [{"token_count": 100}] * k
    return {"experiment_id": "e2", "condition": f"E2-{strategy}", "strategy": strategy,
            "question_id": qid, "question_set": "Q-ret", "question_type": qtype,
            "version": version, "top_k": k, "hit_at_k": hit, "rr_at_k": rr,
            "precision_at_k": hit / k, "contamination_at_k": 0.0,
            "context_tokens": 100 * k, "max_score": 0.5, "chunks_returned": chunks}  # fmt: skip


def test_strategy_scores_and_decision_markdown() -> None:
    questions = (("R1", "v0.3", "API_USAGE"), ("R2", "v1.x", "CONCEPT"))
    rows = [
        _row(s, q, v, t, k, hit, 0.5 * hit)
        for s, hits in (("A", (0, 1)), ("B", (1, 1)))
        for (q, v, t), hit in zip(questions, hits, strict=True)
        for k in (3, 5, 8)
    ]

    scores = strategy_scores(rows)
    assert [(s.strategy, s.hit[5], s.mrr5, s.avg_chunk_tokens5) for s in scores] == [
        ("A", 0.5, 0.25, 100.0),
        ("B", 1.0, 0.5, 100.0),
    ]
    index = ActiveIndex(V03, "v0.3", 7, None, None, 10, None)
    text = decision_markdown(
        Decision("B", 3, ["규칙 1", "K 근거"]),
        scores,
        rows,
        {"A": FenceStats(1, 0), "B": FenceStats(1, 2)},
        {"A": {V03: index}, "B": {V03: index}},
        "2026-11-18",
    )

    assert "- 채택 전략: **B**" in text and "- 운영 Top-K: **3**" in text
    assert "| B | 1.0000 | 1.0000 | 1.0000 | 0.5000 | 0.5000 |" in text
    assert "API_USAGE" in text and "v1.x" in text
    assert "run 7 (10청크)" in text

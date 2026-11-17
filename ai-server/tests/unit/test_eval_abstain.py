"""2단계 방어 측정 — 이벤트 → 결과 분류와 단계별 처리율 집계 (LLM 호출 없음)."""

from typing import Any

from src.config.rag_config import load_rag_config
from src.eval.abstain import (
    Outcome,
    Probe,
    category,
    measure,
    outcome_from_events,
    summarize,
)
from src.pipeline.single import SingleModePipeline
from tests.unit.test_pipeline_single import INDEX, FakeGenerator, FakeSearcher, FakeStream, chunk

OOS = Probe("OOS-006", "Q-oos", "v1.x", "k8s?", True)


def meta(no_context: bool, sources: int = 1) -> dict[str, Any]:
    return {"event": "meta", "requestId": "r", "noContext": no_context,
            "sources": [{}] * (0 if no_context else sources)}  # fmt: skip


def test_low_similarity_is_blocked_at_retrieval() -> None:
    events = [
        meta(True),
        {"event": "done", "status": "NO_CONTEXT", "statusReason": "LOW_SIMILARITY"},
    ]

    o = outcome_from_events(OOS, events)

    assert category(o) == "blocked_similarity" and o.sources == 0


def test_sentinel_is_abstained_and_answer_is_answered() -> None:
    abstain = outcome_from_events(
        OOS, [meta(False), {"event": "done", "status": "NO_CONTEXT", "statusReason": "LLM_ABSTAIN"}]
    )
    answered = outcome_from_events(
        OOS,
        [
            meta(False),
            {"event": "token", "t": "답 "},
            {"event": "token", "t": "[1]"},
            {"event": "done", "status": "COMPLETED", "usage": {"prompt": 1, "completion": 2}},
        ],
    )
    error = outcome_from_events(
        OOS,
        [
            {
                "event": "error",
                "code": "LLM_ERROR",
                "message": "x",
                "requestId": "r",
                "partial": False,
            }
        ],
    )

    assert category(abstain) == "abstained"
    assert (category(answered), answered.answer, answered.tokens) == ("answered", "답 [1]", 2)
    assert (category(error), error.error_code) == ("error", "LLM_ERROR")


def _o(qid: str, qset: str, version: str, reason: str | None, tau_sample: bool = True) -> Outcome:
    status = "NO_CONTEXT" if reason in ("LOW_SIMILARITY", "LLM_ABSTAIN") else "COMPLETED"
    return Outcome(
        qid, qset, version, tau_sample, "done", status, reason, None, 1, 0, "", None, None
    )


def test_summary_counts_two_stage_rate_and_skips_non_tau_samples() -> None:
    outcomes = [
        _o("OOS-001", "Q-oos", "v0.3", "LOW_SIMILARITY"),
        _o("OOS-006", "Q-oos", "v0.3", "LLM_ABSTAIN"),
        _o("OOS-009", "Q-oos", "v0.3", None),
        _o("OOS-008", "Q-oos", "v0.3", "LOW_SIMILARITY", tau_sample=False),  # 제외
        _o("RET-002", "Q-ret", "v0.3", None),
        _o("RET-004", "Q-ret", "v0.3", "LLM_ABSTAIN"),  # 정상 질문 생성 단계 차단
    ]

    rows = {(r["question_set"], r["version"]): r for r in summarize(outcomes)}

    oos = rows[("Q-oos", "v0.3")]
    assert (oos["n"], oos["blocked_similarity"], oos["abstained"], oos["answered"]) == (3, 1, 1, 1)
    assert oos["no_context_rate_l2"] == 1 / 3 and oos["no_context_rate_l2_l3"] == 2 / 3
    ret = rows[("Q-ret", "v0.3")]
    assert (ret["abstained"], ret["no_context_rate_l2_l3"]) == (1, 0.5)


async def test_measure_runs_service_pipeline_per_probe() -> None:
    pipeline = SingleModePipeline(
        FakeSearcher([chunk(1, 0.9)]),
        FakeGenerator(FakeStream(["[[NO_ANSWER]]"])),
        load_rag_config().retrieval,
    )

    [outcome] = await measure(pipeline, {"langchain_v1x": INDEX}, [OOS], "single_v1")

    assert (outcome.question_id, category(outcome)) == ("OOS-006", "abstained")

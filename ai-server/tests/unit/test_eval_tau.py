"""τ 결정 — `eval/decision_rules.md` §3 규칙 (FPR 조건부 F1 최대, 동점 중간값, 반올림)."""

import pytest

from src.eval.tau import decide_tau, f1_nc, round_half_up, scores_by_version


def test_separable_distributions_pick_midpoint_of_gap() -> None:
    ret = [0.50, 0.60, 0.70]
    oos = [0.20, 0.30]

    d = decide_tau(ret, oos)

    # (0.30, 0.50] 전체가 F1=1 → 중간값 0.40
    assert (d.interval.low, d.interval.high) == (0.30, 0.50)
    assert d.tau == 0.40
    assert (d.blocked_ret, d.blocked_oos, d.passed, d.overlap) == (0, 2, True, False)


def test_one_blocked_question_is_allowed_by_fpr_limit() -> None:
    ret = [0.30] + [0.60] * 19  # 0.30 하나를 막으면 FPR 1/20 = 0.05 (허용)
    oos = [0.20, 0.25, 0.40, 0.45]

    d = decide_tau(ret, oos)

    assert (d.interval.low, d.interval.high) == (0.45, 0.60)
    assert d.tau == 0.53  # 0.525 → 반올림
    assert (d.blocked_ret, d.blocked_oos, d.passed) == (1, 4, True)


def test_fpr_limit_binds_when_distributions_overlap() -> None:
    ret = [0.30, 0.32] + [0.60] * 18  # 둘 다 막으면 FPR 0.10 > 0.05
    oos = [0.20, 0.40, 0.45]

    d = decide_tau(ret, oos)

    # FPR 제한이 없으면 (0.45, 0.60]이 F1 최대지만 허용되지 않는다
    assert d.fpr <= 0.05
    assert (d.interval.low, d.interval.high) == (0.20, 0.30)
    assert d.tau == 0.25
    assert d.overlap and not d.passed  # Recall 1/3


def test_lowest_interval_always_satisfies_fpr() -> None:
    d = decide_tau([0.10, 0.12], [0.50])  # Q-oos가 Q-ret보다 위 — 어떤 τ도 Q-oos만 막을 수 없다

    assert d.blocked_ret == 0 and d.blocked_oos == 0
    assert d.tau <= 0.10


def test_round_half_up_avoids_float_artifacts() -> None:
    assert round(0.345, 2) == 0.34  # 내장 round는 표현 오차로 내림
    assert round_half_up(0.345) == 0.35
    assert round_half_up(0.2870) == 0.29


def test_f1_nc_definition() -> None:
    assert f1_nc(1.0, 0.0) == 1.0
    assert f1_nc(0.5, 0.05) == pytest.approx(2 * 0.5 * 0.95 / 1.45)
    assert f1_nc(0.0, 1.0) == 0.0


def test_scores_use_service_condition_once_per_question_and_tau_samples_only() -> None:
    rows = [
        {"condition": "E1-C", "question_id": "RET-001", "version": "v1.x",
         "question_set": "Q-ret", "max_score": 0.6, "top_k": k}
        for k in (3, 5, 8)
    ] + [
        {"condition": "E1-N", "question_id": "RET-001", "version": "v1.x",
         "question_set": "Q-ret", "max_score": 0.9, "top_k": 3},
        {"condition": "E1-C", "question_id": "OOS-001", "version": "v1.x",
         "question_set": "Q-oos", "max_score": 0.2, "top_k": 3},
        {"condition": "E1-C", "question_id": "OOS-008", "version": "v1.x",
         "question_set": "Q-oos", "max_score": 0.1, "top_k": 3},
    ]  # fmt: skip

    scores = scores_by_version(rows, {"OOS-001"})

    assert scores["v1.x"] == ([0.6], [0.2])
    assert scores["v0.3"] == ([], [])


def test_empty_inputs_are_rejected() -> None:
    with pytest.raises(ValueError):
        decide_tau([], [0.2])

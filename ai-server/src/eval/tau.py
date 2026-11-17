"""NO_CONTEXT 임계값 τ 결정 — `eval/decision_rules.md` §3 (eval-v1 고정 규칙).

    uv run python -m src.eval.tau [--results ../eval/results/E1/e1_results.jsonl]

- 입력: 평가 러너 E1 결과(JSONL)의 E1-C(서비스 검색기) 행. 질문의 최대 유사도(`max_score`)만 쓴다.
- Q-ret은 질문 대상 버전 검색만, Q-oos는 τ 표본(`expected_behavior.tau_calibration`)만 쓴다.
- source_key별로 FPR_NC ≤ 0.05를 만족하는 τ 중 F1_NC 최대 구간을 찾고, 동점이면 동점 구간의
  중간값(소수 둘째 자리 반올림)을 τ로 정한다.
- FPR 조건을 만족하는 τ는 항상 있다: 모든 관측값 이하의 τ는 아무것도 막지 않아 FPR_NC = 0이다.
  그래서 결정 규칙 §3-5(만족하는 τ가 없을 때)는 실제로 적용되지 않는다.
- NO_CONTEXT 판정은 서비스와 같다: 최대 유사도 < τ (경계값은 통과).
"""

import argparse
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from src.eval.questions import VERSION_SOURCE_KEYS, load_question_sets, tau_calibration_oos

RESULTS_PATH = Path(__file__).resolve().parents[3] / "eval" / "results" / "E1" / "e1_results.jsonl"
MAX_FPR = 0.05  # decision_rules §3-3
RECALL_TARGET = 0.80  # decision_rules §3 합격 기준
SERVICE_CONDITION = "E1-C"


@dataclass(frozen=True)
class Interval:
    """τ ∈ (low, high] 구간. 이 안의 τ는 NO_CONTEXT 판정 결과가 모두 같다."""

    low: float
    high: float
    fpr: float
    recall: float
    f1: float


@dataclass(frozen=True)
class TauDecision:
    tau: float
    interval: Interval  # 동점 구간을 합친 범위
    n_ret: int
    n_oos: int
    blocked_ret: int  # τ에서 NO_CONTEXT가 된 Q-ret 수 (오차단)
    blocked_oos: int  # τ에서 NO_CONTEXT가 된 Q-oos 수
    overlap: bool  # Q-oos 최대값 ≥ Q-ret 최소값 (두 분포가 겹침)

    @property
    def fpr(self) -> float:
        return self.blocked_ret / self.n_ret

    @property
    def recall(self) -> float:
        return self.blocked_oos / self.n_oos

    @property
    def passed(self) -> bool:
        return self.recall >= RECALL_TARGET and self.fpr <= MAX_FPR


def f1_nc(recall: float, fpr: float) -> float:
    """evaluation.md §2.2 — 2 × Recall × (1 − FPR) / (Recall + (1 − FPR))."""
    specificity = 1.0 - fpr
    total = recall + specificity
    return 0.0 if total == 0 else 2 * recall * specificity / total


def round_half_up(value: float, places: int = 2) -> float:
    """§3-4 "소수 둘째 자리 반올림" — 부동소수점 `round`의 은행가 반올림·표현 오차를 피한다."""
    quantum = Decimal(1).scaleb(-places)
    return float(Decimal(repr(value)).quantize(quantum, rounding=ROUND_HALF_UP))


def intervals(ret: Sequence[float], oos: Sequence[float]) -> list[Interval]:
    """관측값 경계로 나눈 τ 후보 구간 (0, 1] 전체."""
    bounds = [0.0, *sorted(set(ret) | set(oos)), 1.0]
    result = []
    for low, high in zip(bounds, bounds[1:], strict=False):
        if high <= low:
            continue
        fpr = sum(x <= low for x in ret) / len(ret)
        recall = sum(x <= low for x in oos) / len(oos)
        result.append(Interval(low, high, fpr, recall, f1_nc(recall, fpr)))
    return result


def decide_tau(ret: Sequence[float], oos: Sequence[float]) -> TauDecision:
    if not ret or not oos:
        raise ValueError("Q-ret과 Q-oos 최대 유사도가 모두 있어야 τ를 정할 수 있습니다")
    allowed = [c for c in intervals(ret, oos) if c.fpr <= MAX_FPR]  # 첫 구간은 항상 FPR 0
    best = max(c.f1 for c in allowed)
    ties = [c for c in allowed if abs(c.f1 - best) < 1e-12]
    low, high = min(t.low for t in ties), max(t.high for t in ties)
    tau = round_half_up((low + high) / 2)
    if not low < tau <= high:  # 반올림으로 구간을 벗어나면 반올림 전 값을 쓴다
        tau = round_half_up((low + high) / 2, 4)
    return TauDecision(
        tau=tau,
        interval=Interval(low, high, ties[0].fpr, ties[0].recall, best),
        n_ret=len(ret),
        n_oos=len(oos),
        blocked_ret=sum(x < tau for x in ret),
        blocked_oos=sum(x < tau for x in oos),
        overlap=max(oos) >= min(ret),
    )


def scores_by_version(
    rows: Iterable[Mapping[str, Any]], tau_sample_ids: set[str]
) -> dict[str, tuple[list[float], list[float]]]:
    """버전 라벨 → (Q-ret 최대 유사도, Q-oos τ 표본 최대 유사도). 행은 질문·버전마다 하나만 쓴다."""
    seen: set[tuple[str, str]] = set()
    out: dict[str, tuple[list[float], list[float]]] = {v: ([], []) for v in VERSION_SOURCE_KEYS}
    for row in rows:
        if row["condition"] != SERVICE_CONDITION:
            continue
        key = (row["question_id"], row["version"])
        if key in seen:  # K마다 행이 있지만 max_score(top-1)는 같다
            continue
        seen.add(key)
        ret, oos = out[row["version"]]
        if row["question_set"] == "Q-ret":
            ret.append(float(row["max_score"]))
        elif row["question_set"] == "Q-oos" and row["question_id"] in tau_sample_ids:
            oos.append(float(row["max_score"]))
    return out


def report(decisions: Mapping[str, TauDecision]) -> str:
    lines = [
        "| source_key | τ | 동점 구간 | FPR_NC | Recall_NC | F1_NC | 분포 겹침 | 합격 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for label, d in decisions.items():
        source_key = VERSION_SOURCE_KEYS[label]  # type: ignore[index]
        lines.append(
            f"| `{source_key}` | **{d.tau}** | ({d.interval.low:.4f}, "
            f"{d.interval.high:.4f}] | {d.blocked_ret}/{d.n_ret} ({d.fpr:.3f}) | "
            f"{d.blocked_oos}/{d.n_oos} ({d.recall:.3f}) | {d.interval.f1:.4f} | "
            f"{'예' if d.overlap else '아니오'} | {'통과' if d.passed else '미달'} |"
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.eval.tau", description="E1 τ 결정")
    parser.add_argument("--results", type=Path, default=RESULTS_PATH)
    args = parser.parse_args(argv)
    rows = [json.loads(line) for line in args.results.read_text(encoding="utf-8").splitlines()]
    sample_ids = {q.question_id for q in tau_calibration_oos(load_question_sets())}
    decisions = {
        label: decide_tau(ret, oos)
        for label, (ret, oos) in scores_by_version(rows, sample_ids).items()
    }
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:  # Windows 콘솔 기본 인코딩(cp949)에서도 표가 깨지지 않게
        reconfigure(encoding="utf-8")
    print(report(decisions))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

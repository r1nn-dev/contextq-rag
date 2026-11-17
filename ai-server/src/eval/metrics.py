"""검색 품질 지표 — evaluation.md §2.1 (E1·E2) · §2.2 (NO_CONTEXT).

모든 함수는 similarity 내림차순 결과(`RetrievedChunk` 목록)의 앞 K개만 본다.
Precision@K·혼입률의 분모는 반환 개수가 아니라 K다(§2.1 수식).
"""

from collections.abc import Sequence
from dataclasses import dataclass

from src.domain.retrieval import RetrievedChunk
from src.eval.questions import GoldSection


def gold_flags(chunks: Sequence[RetrievedChunk], golds: Sequence[GoldSection]) -> list[bool]:
    """청크마다 gold 섹션 적중 여부 (§2.1 `match(c, g)`)."""
    return [
        any(g.matches(chunk["file_path"], chunk["heading_path"]) for g in golds) for chunk in chunks
    ]


def hit_at_k(flags: Sequence[bool], k: int) -> int:
    return int(any(flags[:k]))


def rr_at_k(flags: Sequence[bool], k: int) -> float:
    for rank, flag in enumerate(flags[:k], start=1):
        if flag:
            return 1.0 / rank
    return 0.0


def precision_at_k(
    chunks: Sequence[RetrievedChunk], flags: Sequence[bool], target_source_key: str, k: int
) -> float:
    relevant = sum(
        1
        for chunk, flag in zip(chunks[:k], flags[:k], strict=True)
        if flag and chunk["source_key"] == target_source_key
    )
    return relevant / k


def contamination_at_k(chunks: Sequence[RetrievedChunk], target_source_key: str, k: int) -> float:
    """Top-K 중 요청 소스가 아닌 청크 비율 (E1 버전 혼입률)."""
    return sum(1 for chunk in chunks[:k] if chunk["source_key"] != target_source_key) / k


def context_tokens(chunks: Sequence[RetrievedChunk], k: int) -> int:
    """Top-K 청크 토큰 수 합 — 평균 컨텍스트 토큰(E2 동률 처리)의 입력."""
    return sum(chunk["token_count"] for chunk in chunks[:k])


def max_score(chunks: Sequence[RetrievedChunk]) -> float | None:
    """최대 similarity — τ 결정용 분포(protocol.md E1 τ 결정 절차)."""
    return max((chunk["similarity"] for chunk in chunks), default=None)


def mean(values: Sequence[float | int | None]) -> float | None:
    """None(해당 없음)을 빼고 평균. 값이 없으면 None."""
    present = [float(v) for v in values if v is not None]
    return sum(present) / len(present) if present else None


@dataclass(frozen=True)
class NoContextMetrics:
    recall: float  # Q-oos 중 NO_CONTEXT 비율
    fpr: float  # Q-ret 중 NO_CONTEXT 오발동 비율
    f1: float


def no_context_metrics(
    ret_max_scores: Sequence[float], oos_max_scores: Sequence[float], tau: float
) -> NoContextMetrics:
    """τ 하나에 대한 Recall_NC·FPR_NC·F1_NC (§2.2). max_score < τ 이면 NO_CONTEXT."""
    if not ret_max_scores or not oos_max_scores:
        raise ValueError("Q-ret·Q-oos 최대 유사도가 모두 있어야 합니다")
    recall = sum(1 for s in oos_max_scores if s < tau) / len(oos_max_scores)
    fpr = sum(1 for s in ret_max_scores if s < tau) / len(ret_max_scores)
    specificity = 1.0 - fpr
    denominator = recall + specificity
    f1 = 2 * recall * specificity / denominator if denominator else 0.0
    return NoContextMetrics(recall=recall, fpr=fpr, f1=f1)

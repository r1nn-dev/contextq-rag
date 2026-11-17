"""토큰 예산 기반 컨텍스트 조립 — 정책서 §5.3 "컨텍스트 채택"·"컨텍스트 예산".

- Top-K 중 similarity ≥ τ 인 청크만 rank 순서대로 넣는다.
- 합계가 예산을 넘으면 낮은 rank부터 뺀다. 청크 중간을 자르지 않는다.
- top-1 하나만으로 예산을 넘으면 top-1만 남긴다(τ를 통과했는데 근거 0개가 되지 않게) + WARNING.
- 고른 청크의 순서가 곧 인용 번호 [1..n]이다 (meta.sources rank, INV-08).
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from src.domain.retrieval import RetrievedChunk
from src.ingest.metadata import count_tokens

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ContextSelection:
    chunks: list[RetrievedChunk]  # rank 순서 = 인용 번호 순서
    total_tokens: int
    below_tau: int  # τ 미만이라 뺀 수
    over_budget: int  # 예산 초과로 뺀 수


def chunk_tokens(chunk: RetrievedChunk) -> int:
    """인덱싱 때 센 `token_count`(tiktoken). 없으면 같은 인코더로 센다."""
    return chunk["token_count"] if chunk["token_count"] > 0 else count_tokens(chunk["content"])


def select_context(
    chunks: Sequence[RetrievedChunk], tau: float, budget_tokens: int
) -> ContextSelection:
    ranked = sorted(chunks, key=lambda c: c["similarity"], reverse=True)
    eligible = [c for c in ranked if c["similarity"] >= tau]
    selected: list[RetrievedChunk] = []
    total = 0
    for chunk in eligible:
        tokens = chunk_tokens(chunk)
        if selected and total + tokens > budget_tokens:
            break  # 이 청크와 그보다 낮은 rank는 모두 뺀다
        selected.append(chunk)
        total += tokens
    if selected and total > budget_tokens:
        logger.warning(
            "context_top1_over_budget",
            extra={
                "event": "context_top1_over_budget",
                "chunk_id": selected[0]["chunk_id"],
                "tokens": total,
                "budget_tokens": budget_tokens,
            },
        )
    return ContextSelection(
        chunks=selected,
        total_tokens=total,
        below_tau=len(ranked) - len(eligible),
        over_budget=len(eligible) - len(selected),
    )

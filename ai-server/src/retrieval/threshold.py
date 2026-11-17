"""NO_CONTEXT 임계값 판정 — ADR-008, 정책서 §5.4.

top-1 similarity < τ(source_key)이거나 결과가 없으면 `LOW_SIMILARITY`다.
이 판정이 나면 생성 LLM을 부르지 않는다(INV-07) — 호출 여부는 스트림 오케스트레이션이 지킨다.
`max_similarity`·`tau`는 서버 로그에만 남기고 클라이언트에 노출하지 않는다 (rag-pipeline.md §4).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from src.domain.retrieval import RetrievedChunk


class NoContextReason(StrEnum):
    """done.statusReason 값 (정책서 §5.4·§10.2)."""

    LOW_SIMILARITY = "LOW_SIMILARITY"  # 검색 단계 차단 — LLM 미호출
    LLM_ABSTAIN = "LLM_ABSTAIN"  # 생성 단계 sentinel — LLM 호출함


@dataclass(frozen=True)
class ThresholdDecision:
    tau: float
    top1_similarity: float | None  # 결과가 없으면 None

    @property
    def passed(self) -> bool:
        return self.top1_similarity is not None and self.top1_similarity >= self.tau

    @property
    def reason(self) -> NoContextReason | None:
        return None if self.passed else NoContextReason.LOW_SIMILARITY


def judge(chunks: Sequence[RetrievedChunk], tau: float) -> ThresholdDecision:
    """top-1 similarity와 τ를 비교한다. 같으면 통과(≥ τ)."""
    top1 = max((c["similarity"] for c in chunks), default=None)
    return ThresholdDecision(tau=tau, top1_similarity=top1)

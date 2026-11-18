"""E2 청킹 전략 비교 — 전략별 run 선택·코드 블록 보존율·결정 규칙 적용 (protocol.md 실험 E2).

- 검색은 E1-C와 같은 서비스 검색기(`ChromaRetriever`)로 하고, 전략·버전마다 run을 고정한다.
- 결정 규칙은 `eval/decision_rules.md` §1·§2를 그대로 옮긴다(eval-v1 태그 이후 변경 금지).
  §1: Hit@5 최고 → 1·2위 차이 < 3%p면 MRR@5 → 평균 컨텍스트 토큰(적은 쪽).
  §2: 채택 전략에서 Hit@5 − Hit@3 < 2%p면 K=3, 아니고 Hit@8 − Hit@5 < 2%p면 K=5, 아니면 K=8.
- 값이 "같다"는 소수 넷째 자리까지 같다는 뜻이다(decision_rules.md §1 노트).
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.ingest_status import IngestStatus
from src.domain.tables import IngestRun, Source
from src.retrieval.pointers import ActiveIndex, ingested_on

STRATEGIES = ("A", "B", "C")
# 컬렉션이 남아 있는 상태 — PURGED·FAILED·진행 중 run은 검색할 수 없다
SEARCHABLE = (IngestStatus.ACTIVE, IngestStatus.READY, IngestStatus.SUPERSEDED)
TIE_MARGIN = 0.03  # decision_rules.md §1 규칙 2 — Hit@5 3%p
K_GAIN_MARGIN = 0.02  # decision_rules.md §2 — Hit@K 증가폭 2%p
FENCE = "```"


class StrategyRunsMissingError(LookupError):
    """전략·버전 조합 중 검색할 수 있는 run이 없음 — 먼저 `make ingest STRATEGY=...`."""


def run_index(session: Session, run: IngestRun) -> ActiveIndex:
    """임의 run(ACTIVE가 아니어도)의 검색 스냅샷 — 평가 러너가 run을 고정할 때 쓴다."""
    source = session.scalar(select(Source).where(Source.source_key == run.source_key))
    if source is None:
        raise StrategyRunsMissingError(f"등록되지 않은 소스입니다: {run.source_key}")
    return ActiveIndex(
        source_key=run.source_key,
        version=source.version_label,
        run_id=run.id,
        commit_sha=run.commit_sha,
        ingested_at=ingested_on(run),
        chunk_count=run.chunk_count,
        embedding_model=run.embedding_model,
        display_name=source.display_name,
    )


def strategy_indexes(
    session: Session, source_keys: Sequence[str], strategies: Sequence[str] = STRATEGIES
) -> dict[str, dict[str, ActiveIndex]]:
    """전략 → 소스 → 검색할 run. 같은 조합이 여러 개면 가장 최근 run(ACTIVE 우선)."""
    found: dict[str, dict[str, ActiveIndex]] = {s: {} for s in strategies}
    missing: list[str] = []
    for strategy in strategies:
        for source_key in source_keys:
            runs = session.scalars(
                select(IngestRun)
                .where(
                    IngestRun.source_key == source_key,
                    IngestRun.chunk_strategy == strategy,
                    IngestRun.status.in_([str(s) for s in SEARCHABLE]),
                )
                .order_by(IngestRun.id.desc())
            ).all()
            if not runs:
                missing.append(f"{source_key}/{strategy}")
                continue
            chosen = next((r for r in runs if r.status == IngestStatus.ACTIVE), runs[0])
            found[strategy][source_key] = run_index(session, chosen)
    if missing:
        raise StrategyRunsMissingError(f"검색할 수 있는 전략별 run이 없습니다: {missing}")
    return found


@dataclass(frozen=True)
class FenceStats:
    """코드 펜스 보존 — 펜스 수가 짝수인 청크는 펜스가 그 안에서 열리고 닫힌다.

    `split_chunks`는 펜스 수가 홀수인 청크(펜스가 다른 청크로 이어짐) 수다. 쪼개진 펜스 하나는
    보통 두 청크에 걸치므로 보존율은 `complete / (complete + split_chunks / 2)`로 계산한다.
    """

    complete: int
    split_chunks: int

    @property
    def preservation(self) -> float | None:
        total = self.complete + self.split_chunks / 2
        return self.complete / total if total else None


def fence_stats(documents: Iterable[str]) -> FenceStats:
    complete = split = 0
    for text in documents:
        fences = text.count(FENCE)
        complete += fences // 2
        split += fences % 2
    return FenceStats(complete, split)


@dataclass(frozen=True)
class StrategyScore:
    """한 전략의 Q-ret 전체(두 버전) 지표."""

    strategy: str
    hit: Mapping[int, float]  # K → Hit@K
    mrr5: float
    avg_chunk_tokens5: float  # Top-5 청크 token_count 평균


@dataclass(frozen=True)
class Decision:
    strategy: str
    top_k: int
    reasons: list[str] = field(default_factory=list)


def _r4(value: float) -> float:
    return round(value, 4)


def choose_strategy(scores: Sequence[StrategyScore]) -> tuple[str, list[str]]:
    """decision_rules.md §1. 근거 문장을 함께 돌려준다."""
    ranked = sorted(scores, key=lambda s: (-_r4(s.hit[5]), s.strategy))
    first, second = ranked[0], ranked[1]
    gap = _r4(first.hit[5] - second.hit[5])
    reasons = [
        f"규칙 1: Hit@5 1위 {first.strategy}({first.hit[5]:.4f}), "
        f"2위 {second.strategy}({second.hit[5]:.4f}), 차이 {gap * 100:.2f}%p"
    ]
    if gap >= TIE_MARGIN:
        reasons.append(f"차이 ≥ 3%p → {first.strategy} 채택")
        return first.strategy, reasons
    # 규칙 2는 1·2위만 비교한다 (decision_rules.md §1 "1·2위 Hit@5 차이")
    contenders = [first, second]
    reasons.append(
        "차이 < 3%p → 규칙 2: 후보 "
        + ", ".join(f"{s.strategy}(MRR@5 {s.mrr5:.4f})" for s in contenders)
    )
    best_mrr = max(_r4(s.mrr5) for s in contenders)
    by_mrr = [s for s in contenders if _r4(s.mrr5) == best_mrr]
    if len(by_mrr) == 1:
        reasons.append(f"MRR@5 최고 → {by_mrr[0].strategy} 채택")
        return by_mrr[0].strategy, reasons
    winner = min(by_mrr, key=lambda s: (_r4(s.avg_chunk_tokens5), s.strategy))
    reasons.append(
        "MRR@5 동률 → 평균 컨텍스트 토큰 "
        + ", ".join(f"{s.strategy} {s.avg_chunk_tokens5:.1f}" for s in by_mrr)
        + f" → {winner.strategy} 채택"
    )
    return winner.strategy, reasons


def choose_k(score: StrategyScore) -> tuple[int, list[str]]:
    """decision_rules.md §2 — 바로 다음 K와의 Hit 증가폭이 2%p 미만인 최소 K."""
    gain_5 = _r4(score.hit[5] - score.hit[3])
    gain_8 = _r4(score.hit[8] - score.hit[5])
    text = (
        f"K: Hit@3 {score.hit[3]:.4f} · Hit@5 {score.hit[5]:.4f} · Hit@8 {score.hit[8]:.4f} "
        f"(5−3 {gain_5 * 100:.2f}%p, 8−5 {gain_8 * 100:.2f}%p)"
    )
    if gain_5 < K_GAIN_MARGIN:
        return 3, [text, "Hit@5 − Hit@3 < 2%p → K=3"]
    if gain_8 < K_GAIN_MARGIN:
        return 5, [text, "Hit@5 − Hit@3 ≥ 2%p, Hit@8 − Hit@5 < 2%p → K=5"]
    return 8, [text, "두 증가폭 모두 ≥ 2%p → K=8"]


def decide(scores: Sequence[StrategyScore]) -> Decision:
    if len(scores) < 2:
        raise ValueError("전략이 2개 이상이어야 비교할 수 있습니다")
    strategy, reasons = choose_strategy(scores)
    chosen = next(s for s in scores if s.strategy == strategy)
    top_k, k_reasons = choose_k(chosen)
    return Decision(strategy, top_k, reasons + k_reasons)

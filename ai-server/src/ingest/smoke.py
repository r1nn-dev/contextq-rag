"""활성 인덱스 스모크 재실행 — 정책서 §4.4 · `eval/decision_rules.md` §3-7 (τ가 바뀌면 다시 실행).

검증 게이트와 같은 `check_smoke`를 ACTIVE run 컬렉션에 다시 돌린다. 상태는 바꾸지 않는다.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from src.config.ingest_config import SmokeConfig
from src.ingest.embedder import EmbeddingClient
from src.ingest.store import VectorStore
from src.ingest.validate import CheckResult, check_smoke
from src.retrieval.pointers import load_active_index


@dataclass(frozen=True)
class SmokeOutcome:
    source_key: str
    run_id: int
    tau: float
    result: CheckResult


def run_smoke(
    session: Session,
    store: VectorStore,
    embedder: EmbeddingClient,
    smoke: SmokeConfig,
    tau_for: Callable[[str], float],
    sources: Iterable[str],
) -> list[SmokeOutcome]:
    outcomes = []
    for source_key in sources:
        index = load_active_index(session, source_key)
        tau = tau_for(source_key)
        result = check_smoke(
            store,
            index.collection,
            embedder,
            smoke.sources.get(source_key, []),
            tau=tau,
            top_k=smoke.top_k,
        )
        outcomes.append(SmokeOutcome(source_key, index.run_id, tau, result))
    return outcomes


def format_outcome(outcome: SmokeOutcome) -> str:
    detail = outcome.result.detail
    status = "통과" if outcome.result.passed else "실패"
    lines = [
        f"{outcome.source_key} run {outcome.run_id} τ={outcome.tau}: {status} "
        f"({detail.get('passed', 0)}/{detail.get('total', 0)})"
    ]
    for item in detail.get("results", []):
        mark = "O" if item["passed"] else "X"
        lines.append(
            f"  [{mark}] top1={item['top1_similarity']} rank={item['rank']} {item['question']}"
        )
    return "\n".join(lines)

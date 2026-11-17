"""2단계 방어 측정 — 검색 단계 τ 차단(LOW_SIMILARITY) + 생성 단계 근거 부족 판정(LLM_ABSTAIN).

    uv run python -m src.eval.abstain [--out ../eval/results/E1/e1_l3_results.jsonl]

- 서비스와 같은 `SingleModePipeline`(실제 검색기·생성기, `configs/rag.yaml` τ)을 그대로 돌린다.
- Q-oos 10문항 × 두 버전, Q-ret 40문항 × 대상 버전. 생성 LLM은 τ를 통과한 질문에서만 호출된다.
- 정책서 §5.4: 기획서 처리율 지표는 LOW_SIMILARITY만 센다. 이 측정은 LLM_ABSTAIN을 더한
  2단계 처리율과, 정상 질문이 생성 단계에서 막히는 비율(성능 손실)을 따로 보고한다.
- DB(ACTIVE 포인터)·Chroma 인덱스·OpenAI 키가 필요하다 → 사용자 터미널에서 실행.
"""

import argparse
import asyncio
import json
import sys
import time
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.config.ingest_config import load_embedding_config
from src.config.rag_config import load_llm_config, load_rag_config
from src.config.settings import Settings
from src.eval.questions import VERSION_SOURCE_KEYS, load_question_sets, tau_calibration_oos
from src.eval.run import active_indexes
from src.ingest.store import ChromaVectorStore
from src.pipeline.generator import OpenAIAnswerGenerator
from src.pipeline.single import SingleModePipeline, SingleRequest, StreamProgress
from src.retrieval.embedding import OpenAIQueryEmbedder
from src.retrieval.pointers import ActiveIndex, StaticPointers
from src.retrieval.search import ChromaRetriever

OUT_PATH = Path(__file__).resolve().parents[3] / "eval" / "results" / "E1" / "e1_l3_results.jsonl"
CONCURRENCY = 4  # OpenAI 요청 동시 수 (측정 시간 단축용, 결과에는 영향 없음)


@dataclass(frozen=True)
class Probe:
    question_id: str
    question_set: str  # Q-ret | Q-oos
    version: str
    query: str
    tau_calibration: bool  # Q-oos τ 표본 여부 (Q-ret은 True)


@dataclass(frozen=True)
class Outcome:
    question_id: str
    question_set: str
    version: str
    tau_calibration: bool
    terminal: str  # done | error
    status: str | None  # COMPLETED | PARTIAL | NO_CONTEXT | FAILED
    status_reason: str | None  # LOW_SIMILARITY | LLM_ABSTAIN | LENGTH | ...
    error_code: str | None
    sources: int
    tokens: int
    answer: str
    model: str | None
    usage: Mapping[str, int] | None


def probes(tau_sample_ids: set[str]) -> list[Probe]:
    sets = load_question_sets()
    items = [Probe(q.question_id, "Q-ret", q.target_version, q.query, True) for q in sets.ret]
    for q in sets.oos:
        for version in VERSION_SOURCE_KEYS:
            items.append(
                Probe(q.question_id, "Q-oos", version, q.query, q.question_id in tau_sample_ids)
            )
    return items


def outcome_from_events(probe: Probe, events: Sequence[Mapping[str, Any]]) -> Outcome:
    meta = next((e for e in events if e["event"] == "meta"), None)
    tokens = [e["t"] for e in events if e["event"] == "token"]
    last = events[-1]
    done = last if last["event"] == "done" else None
    return Outcome(
        question_id=probe.question_id,
        question_set=probe.question_set,
        version=probe.version,
        tau_calibration=probe.tau_calibration,
        terminal=last["event"],
        status=done["status"] if done else None,
        status_reason=done.get("statusReason") if done else None,
        error_code=None if done else last.get("code"),
        sources=len(meta["sources"]) if meta else 0,
        tokens=len(tokens),
        answer="".join(tokens),
        model=done.get("model") if done else None,
        usage=done.get("usage") if done else None,
    )


def category(o: Outcome) -> str:
    """blocked_similarity | abstained | answered | error."""
    if o.terminal == "error":
        return "error"
    if o.status == "NO_CONTEXT" and o.status_reason == "LOW_SIMILARITY":
        return "blocked_similarity"
    if o.status == "NO_CONTEXT" and o.status_reason == "LLM_ABSTAIN":
        return "abstained"
    return "answered"


def summarize(outcomes: Iterable[Outcome]) -> list[dict[str, Any]]:
    """(질문셋, 버전)별 단계별 처리 수. Q-oos는 τ 표본만 센다."""
    groups: dict[tuple[str, str], list[Outcome]] = {}
    for o in outcomes:
        if o.question_set == "Q-oos" and not o.tau_calibration:
            continue
        groups.setdefault((o.question_set, o.version), []).append(o)
    rows = []
    for (question_set, version), members in sorted(groups.items()):
        counts = {c: sum(category(m) == c for m in members) for c in
                  ("blocked_similarity", "abstained", "answered", "error")}  # fmt: skip
        total = len(members)
        no_context = counts["blocked_similarity"] + counts["abstained"]
        rows.append(
            {
                "question_set": question_set,
                "version": version,
                "n": total,
                **counts,
                "no_context_rate_l2": counts["blocked_similarity"] / total,
                "no_context_rate_l2_l3": no_context / total,
            }
        )
    return rows


async def measure(
    pipeline: SingleModePipeline,
    indexes: Mapping[str, ActiveIndex],
    items: Sequence[Probe],
    prompt_version: str,
) -> list[Outcome]:
    slots = asyncio.Semaphore(CONCURRENCY)

    async def one(probe: Probe) -> Outcome:
        source_key = VERSION_SOURCE_KEYS[probe.version]  # type: ignore[index]
        request = SingleRequest(
            f"l3-{uuid.uuid4()}", probe.query, indexes[source_key], prompt_version
        )
        async with slots:
            progress = StreamProgress(started=time.perf_counter())
            events = [e async for e in pipeline.run(request, progress)]
        return outcome_from_events(probe, events)

    return list(await asyncio.gather(*(one(p) for p in items)))


def main(argv: Sequence[str] | None = None, settings: Settings | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.eval.abstain")
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args = parser.parse_args(argv)
    settings = settings or Settings()
    sets = load_question_sets()
    tau_ids = {q.question_id for q in tau_calibration_oos(sets)}

    engine = create_engine(settings.database_url)
    try:
        with Session(engine) as session:
            indexes = active_indexes(session)
    finally:
        engine.dispose()
    config = load_rag_config()
    retriever = ChromaRetriever(
        ChromaVectorStore(settings.chroma_data_dir),
        StaticPointers(indexes),
        OpenAIQueryEmbedder(settings.openai_api_key, load_embedding_config()),
    )
    generator = OpenAIAnswerGenerator(
        settings.openai_api_key, load_llm_config(), model_override=settings.llm_model
    )
    pipeline = SingleModePipeline(
        retriever, generator, config.retrieval, tau_overrides=settings.tau_overrides()
    )
    outcomes = asyncio.run(
        measure(pipeline, indexes, probes(tau_ids), config.generation.prompt_version)
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="\n") as f:
        for o in outcomes:
            f.write(json.dumps(asdict(o), ensure_ascii=False) + "\n")
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8")
    taus = {key: config.retrieval.tau(key, settings.tau_overrides()) for key in indexes}
    print(f"τ: {taus} · 결과: {args.out}")
    for row in summarize(outcomes):
        print(
            f"{row['question_set']} {row['version']} n={row['n']} "
            f"τ차단={row['blocked_similarity']} 근거부족={row['abstained']} "
            f"답변={row['answered']} 오류={row['error']} "
            f"처리율(τ)={row['no_context_rate_l2']:.3f} "
            f"처리율(τ+생성)={row['no_context_rate_l2_l3']:.3f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""검색 평가 러너 — E1(버전 격리)·E2(청킹 전략) 결과 JSONL·요약 CSV (evaluation.md §3·§4).

    uv run python -m src.eval.run --exp E1 [--conditions N F C] [--out-dir ../eval/results]
    uv run python -m src.eval.run --check        # 질문셋 스키마·v1 구성·검수 상태만 확인

- 검색은 `Retriever` 계약(interfaces.md §4)으로만 한다. E1-C·E2는 서비스 Retriever를 쓰고,
  E1-N·E1-F는 실험용 병합 컬렉션 검색기를 쓴다(conditions.py).
- E1-C는 서비스 검색기(`ChromaRetriever`)를 그대로 쓴다. 실행 시작 때 확정한 ACTIVE run으로
  고정하고, 질의 임베딩은 N·F와 같은 값을 넣는다(조건 간 임베딩 차이 제거).
- E2는 전략(A·B·C)·버전마다 검색할 수 있는 run을 하나씩 고정해 서비스 검색기로 Q-ret만 검색하고,
  결정 규칙(e2.py)을 적용한 결과를 `decision.md`로 남긴다.
- Q-ret는 질문의 target_version 컬렉션에서, Q-oos는 두 버전 컬렉션에서 각각 검색한다.
"""

import argparse
import asyncio
import csv
import json
import platform
import subprocess
import sys
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.config.ingest_config import load_embedding_config
from src.config.settings import Settings
from src.domain.retrieval import RetrievedChunk, Retriever
from src.eval.conditions import (
    E1_CONDITIONS,
    Condition,
    MergedCollectionSearcher,
    PrecomputedQueryEmbedder,
    build_merged_collection,
    embed_queries,
    merged_collection_name,
)
from src.eval.e2 import (
    STRATEGIES,
    Decision,
    FenceStats,
    StrategyRunsMissingError,
    StrategyScore,
    decide,
    fence_stats,
    strategy_indexes,
)
from src.eval.metrics import (
    contamination_at_k,
    context_tokens,
    gold_flags,
    hit_at_k,
    max_score,
    mean,
    precision_at_k,
    rr_at_k,
)
from src.eval.questions import (
    VERSION_SOURCE_KEYS,
    OosQuestion,
    QuestionSets,
    RetQuestion,
    load_question_sets,
    unreviewed,
    v1_composition_errors,
)
from src.ingest.embedder import OpenAIEmbeddingClient
from src.ingest.store import ChromaVectorStore, VectorStore
from src.retrieval.errors import RetrievalError
from src.retrieval.pointers import ActiveIndex, StaticPointers, load_active_index
from src.retrieval.search import ChromaRetriever

RESULTS_DIR = Path(__file__).resolve().parents[3] / "eval" / "results"
DEFAULT_KS = (3, 5, 8)
EXPERIMENTS = ("E1", "E2")
_SOURCE_VERSIONS = {source_key: label for label, source_key in VERSION_SOURCE_KEYS.items()}
_SUMMARY_FIELDS = (
    "experiment_id",
    "condition",
    "question_set",
    "version",
    "top_k",
    "n",
    "hit_at_k",
    "mrr_at_k",
    "precision_at_k",
    "contamination_at_k",
    "avg_context_tokens",
    "max_score_mean",
)


class RetrieverUnavailableError(RuntimeError):
    """실험에 필요한 인덱스·검색기가 아직 없음 (E2: 전략별 인덱스, R-7-3)."""


# --- 행 단위 평가 -----------------------------------------------------------


def _chunk_rows(chunks: Sequence[RetrievedChunk], flags: Sequence[bool]) -> list[dict[str, Any]]:
    return [
        {
            "chunk_id": c["chunk_id"],
            "source_key": c["source_key"],
            "file_path": c["file_path"],
            "heading_path": c["heading_path"],
            "similarity": round(c["similarity"], 6),
            "token_count": c["token_count"],
            "is_gold": flag,
        }
        for c, flag in zip(chunks, flags, strict=True)
    ]


def evaluate(
    searcher: Retriever,
    ret: Iterable[RetQuestion],
    oos: Iterable[OosQuestion],
    *,
    experiment_id: str,
    condition: str,
    ks: Sequence[int] = DEFAULT_KS,
    run_date: str | None = None,
) -> list[dict[str, Any]]:
    """질문 × (버전) × K 마다 한 행. 검색은 질문당 max(K)로 한 번만 하고 앞 K개로 자른다."""
    run_date = run_date or date.today().isoformat()
    top = max(ks)
    rows: list[dict[str, Any]] = []
    base = {"experiment_id": experiment_id, "run_date": run_date, "condition": condition}

    def emit(
        question_id: str,
        question_set: str,
        question_type: str,
        source_key: str,
        chunks: list[RetrievedChunk],
        flags: list[bool] | None,
    ) -> None:
        for k in ks:
            head = chunks[:k]
            rows.append(
                {
                    **base,
                    "question_id": question_id,
                    "question_set": question_set,
                    "question_type": question_type,
                    "version": _SOURCE_VERSIONS[source_key],
                    "top_k": k,
                    "max_score": max_score(head),
                    "tau": None,
                    "no_context_triggered": None,
                    "chunks_returned": _chunk_rows(head, (flags or [False] * len(chunks))[:k]),
                    "hit_at_k": hit_at_k(flags, k) if flags is not None else None,
                    "rr_at_k": rr_at_k(flags, k) if flags is not None else None,
                    "precision_at_k": (
                        precision_at_k(chunks, flags, source_key, k) if flags is not None else None
                    ),
                    "contamination_at_k": contamination_at_k(chunks, source_key, k),
                    "context_tokens": context_tokens(chunks, k),
                }
            )

    for q in ret:
        chunks = searcher.retrieve(q.query, q.source_key, top)
        flags = gold_flags(chunks, q.gold.sections)
        emit(q.question_id, "Q-ret", q.type, q.source_key, chunks, flags)
    for oq in oos:
        for source_key in VERSION_SOURCE_KEYS.values():
            chunks = searcher.retrieve(oq.query, source_key, top)
            emit(oq.question_id, "Q-oos", oq.type, source_key, chunks, None)
    return rows


def summarize(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """(실험, 조건, 질문셋, 버전, K)별 평균. 버전 `all`은 두 버전 합계."""
    groups: dict[tuple[str, str, str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        for version in (row["version"], "all"):
            key = (
                row["experiment_id"],
                row["condition"],
                row["question_set"],
                version,
                row["top_k"],
            )
            groups[key].append(row)
    summary = []
    for (experiment_id, condition, question_set, version, k), members in sorted(groups.items()):
        summary.append(
            {
                "experiment_id": experiment_id,
                "condition": condition,
                "question_set": question_set,
                "version": version,
                "top_k": k,
                "n": len(members),
                "hit_at_k": mean([m["hit_at_k"] for m in members]),
                "mrr_at_k": mean([m["rr_at_k"] for m in members]),
                "precision_at_k": mean([m["precision_at_k"] for m in members]),
                "contamination_at_k": mean([m["contamination_at_k"] for m in members]),
                "avg_context_tokens": mean([m["context_tokens"] for m in members]),
                "max_score_mean": mean([m["max_score"] for m in members]),
            }
        )
    return summary


# --- 출력 ---------------------------------------------------------------------


def write_results(
    out_dir: Path, experiment: str, rows: list[dict[str, Any]], env: Mapping[str, Any]
) -> tuple[Path, Path]:
    target = out_dir / experiment
    target.mkdir(parents=True, exist_ok=True)
    prefix = experiment.lower()
    rows_path = target / f"{prefix}_results.jsonl"
    with rows_path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary_path = target / f"{prefix}_summary.csv"
    with summary_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_SUMMARY_FIELDS)
        writer.writeheader()
        for line in summarize(rows):
            writer.writerow({k: _fmt(v) for k, v in line.items()})
    (target / "env.txt").write_text(
        "".join(f"{k}: {v}\n" for k, v in env.items()), encoding="utf-8", newline="\n"
    )
    return rows_path, summary_path


def _fmt(value: Any) -> Any:
    return f"{value:.4f}" if isinstance(value, float) else ("" if value is None else value)


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=10
        )
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


# --- E1 -----------------------------------------------------------------------


def active_indexes(session: Session) -> dict[str, ActiveIndex]:
    """평가 대상 소스의 ACTIVE run 스냅샷 — 서비스와 같은 포인터 조회 함수를 쓴다."""
    found: dict[str, ActiveIndex] = {}
    errors: list[str] = []
    for source_key in VERSION_SOURCE_KEYS.values():
        try:
            found[source_key] = load_active_index(session, source_key)
        except RetrievalError as exc:
            errors.append(f"{source_key}: {exc}")
    if errors:
        raise LookupError(f"ACTIVE run을 확인할 수 없는 소스: {errors}")
    return found


@dataclass(frozen=True)
class E1Inputs:
    store: VectorStore
    indexes: Mapping[str, ActiveIndex]
    embeddings: Mapping[str, Sequence[float]]
    embedding_model: str

    @property
    def runs(self) -> dict[str, int]:
        return {key: index.run_id for key, index in self.indexes.items()}


def service_retriever(inputs: E1Inputs) -> ChromaRetriever:
    """E1-C — 운영 검색기를 실행 시작 때 확정한 run과 미리 계산한 질의 임베딩으로 만든다."""
    embedder = PrecomputedQueryEmbedder(inputs.embeddings, inputs.embedding_model)
    return ChromaRetriever(inputs.store, StaticPointers(inputs.indexes), embedder)


def e1_searchers(inputs: E1Inputs, conditions: Sequence[Condition]) -> dict[str, Retriever]:
    """조건 코드 → 검색기. N·F가 있으면 병합 컬렉션을 만든다(있으면 재사용)."""
    searchers: dict[str, Retriever] = {}
    if "N" in conditions or "F" in conditions:
        name = merged_collection_name(inputs.runs)
        sources = {key: index.collection for key, index in inputs.indexes.items()}
        build_merged_collection(inputs.store, sources, name)
        for code in ("N", "F"):
            if code in conditions:
                searchers[f"E1-{code}"] = MergedCollectionSearcher(
                    inputs.store, name, inputs.embeddings, filter_by_source=code == "F"
                )
    if "C" in conditions:
        searchers["E1-C"] = service_retriever(inputs)
    return searchers


def run_e1(
    settings: Settings,
    sets: QuestionSets,
    conditions: Sequence[Condition],
    out_dir: Path,
    ks: Sequence[int],
) -> tuple[Path, Path]:
    engine = create_engine(settings.database_url)
    try:
        with Session(engine) as session:
            indexes = active_indexes(session)
    finally:
        engine.dispose()
    store = ChromaVectorStore(settings.chroma_data_dir)
    embedding_config = load_embedding_config()
    queries = [q.query for q in sets.ret] + [q.query for q in sets.oos]
    embedder = OpenAIEmbeddingClient(settings.openai_api_key, embedding_config)
    embeddings = asyncio.run(embed_queries(embedder, queries))
    inputs = E1Inputs(store, indexes, embeddings, embedding_config.model)
    searchers = e1_searchers(inputs, conditions)
    rows = [
        row
        for condition, searcher in searchers.items()
        for row in evaluate(
            searcher, sets.ret, sets.oos, experiment_id="e1", condition=condition, ks=ks
        )
    ]
    env = {
        "experiment": "E1",
        "date": date.today().isoformat(),
        "git_commit": _git_commit(),
        "python": platform.python_version(),
        "embedding_model": embedding_config.model,
        "active_runs": ", ".join(
            f"{k}=run{v.run_id}@{(v.commit_sha or '')[:7]}" for k, v in sorted(indexes.items())
        ),
        "conditions": ", ".join(searchers),
        "top_k": ", ".join(str(k) for k in ks),
        "questions": ", ".join(f"{k}={v}" for k, v in sets.counts().items()),
        "unreviewed_questions": len(unreviewed(sets)),
    }
    return write_results(out_dir, "E1", rows, env)


# --- E2 -----------------------------------------------------------------------

E2_KS = (3, 5, 8)  # decision_rules.md §2 K 후보


def strategy_scores(rows: Sequence[Mapping[str, Any]]) -> list[StrategyScore]:
    """전략별 Q-ret 전체 지표 — Hit@K·MRR@5·Top-5 청크 평균 토큰."""
    by: dict[str, dict[int, list[Mapping[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if row["question_set"] == "Q-ret":
            by[row["strategy"]][row["top_k"]].append(row)
    scores = []
    for strategy, per_k in sorted(by.items()):
        five = per_k[5]
        per_chunk = [
            r["context_tokens"] / len(r["chunks_returned"]) for r in five if r["chunks_returned"]
        ]
        scores.append(
            StrategyScore(
                strategy=strategy,
                hit={k: mean([r["hit_at_k"] for r in per_k[k]]) or 0.0 for k in E2_KS},
                mrr5=mean([r["rr_at_k"] for r in five]) or 0.0,
                avg_chunk_tokens5=mean(per_chunk) or 0.0,
            )
        )
    return scores


def _breakdown(rows: Sequence[Mapping[str, Any]], key: str) -> dict[tuple[str, str], float | None]:
    """(전략, 키 값) → Hit@5. 키는 `question_type` 또는 `version`."""
    groups: dict[tuple[str, str], list[Any]] = defaultdict(list)
    for row in rows:
        if row["question_set"] == "Q-ret" and row["top_k"] == 5:
            groups[(row["strategy"], row[key])].append(row["hit_at_k"])
    return {k: mean(v) for k, v in groups.items()}


def _num(value: float | None) -> str:
    return "-" if value is None else f"{value:.4f}"


def decision_markdown(
    decision: Decision,
    scores: Sequence[StrategyScore],
    rows: Sequence[dict[str, Any]],
    fences: Mapping[str, FenceStats],
    runs: Mapping[str, Mapping[str, ActiveIndex]],
    run_date: str,
) -> str:
    """`eval/results/E2/decision.md` — 결정·규칙 적용 근거·비교표·하위 분석·사용 run."""
    summary = {
        (line["condition"], line["version"], line["top_k"]): line
        for line in summarize(rows)
        if line["question_set"] == "Q-ret"
    }
    lines = [
        "# E2 결정 기록 — 청킹 전략·운영 Top-K",
        "",
        f"> 실행일 {run_date} · 질문셋 eval-v1 Q-ret · 규칙 `eval/decision_rules.md` §1·§2"
        " (적용 코드 `ai-server/src/eval/e2.py`)",
        "",
        "## 결정",
        "",
        f"- 채택 전략: **{decision.strategy}**",
        f"- 운영 Top-K: **{decision.top_k}**",
        "",
        "### 규칙 적용",
        "",
        *[f"{i}. {reason}" for i, reason in enumerate(decision.reasons, start=1)],
        "",
        "## 전략 × K 비교 (Q-ret, 두 버전 합계)",
        "",
        "| 전략 | Hit@3 | Hit@5 | Hit@8 | MRR@3 | MRR@5 | Precision@5"
        " | Top-5 청크 평균 토큰 | 코드 블록 보존율 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for score in scores:
        s = score.strategy
        cond = f"E2-{s}"
        lines.append(
            f"| {s} | {_num(score.hit[3])} | {_num(score.hit[5])} | {_num(score.hit[8])}"
            f" | {_num(summary[(cond, 'all', 3)]['mrr_at_k'])} | {_num(score.mrr5)}"
            f" | {_num(summary[(cond, 'all', 5)]['precision_at_k'])}"
            f" | {score.avg_chunk_tokens5:.1f} | {_num(fences[s].preservation)} |"
        )
    by_version = _breakdown(rows, "version")
    by_type = _breakdown(rows, "question_type")
    columns = sorted({v for _, v in by_version}) + sorted({t for _, t in by_type})
    merged = {**by_version, **by_type}
    lines += [
        "",
        "## 하위 분석 — Hit@5 (버전·질문 유형)",
        "",
        "| 전략 | " + " | ".join(columns) + " |",
        "| --- |" + " --- |" * len(columns),
    ]
    for score in scores:
        cells = [_num(merged.get((score.strategy, c))) for c in columns]
        lines.append(f"| {score.strategy} | " + " | ".join(cells) + " |")
    sources = sorted(next(iter(runs.values())))
    lines += [
        "",
        "## 사용한 run",
        "",
        "| 전략 | " + " | ".join(sources) + " |",
        "| --- |" + " --- |" * len(sources),
    ]
    for s in sorted(runs):
        cells = [f"run {runs[s][k].run_id} ({runs[s][k].chunk_count}청크)" for k in sources]
        lines.append(f"| {s} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "- 코드 블록 보존율: 펜스 수가 짝수인 청크의 완결 펜스 수"
        " ÷ (완결 펜스 + 펜스 수가 홀수인 청크 ÷ 2).",
        "- Top-5 청크 평균 토큰: 질문별 Top-5 `token_count` 평균의 평균(결정 규칙 §1 동률 기준).",
        "",
    ]
    return "\n".join(lines)


def run_e2(settings: Settings, sets: QuestionSets, out_dir: Path) -> tuple[Path, Path]:
    engine = create_engine(settings.database_url)
    try:
        with Session(engine) as session:
            runs = strategy_indexes(session, list(VERSION_SOURCE_KEYS.values()))
    finally:
        engine.dispose()
    store = ChromaVectorStore(settings.chroma_data_dir)
    embedding_config = load_embedding_config()
    embedder = OpenAIEmbeddingClient(settings.openai_api_key, embedding_config)
    embeddings = asyncio.run(embed_queries(embedder, [q.query for q in sets.ret]))
    query_embedder = PrecomputedQueryEmbedder(embeddings, embedding_config.model)
    run_date = date.today().isoformat()
    rows: list[dict[str, Any]] = []
    fences: dict[str, FenceStats] = {}
    for strategy in STRATEGIES:
        retriever = ChromaRetriever(store, StaticPointers(runs[strategy]), query_embedder)
        for row in evaluate(
            retriever,
            sets.ret,
            [],
            experiment_id="e2",
            condition=f"E2-{strategy}",
            ks=E2_KS,
            run_date=run_date,
        ):
            rows.append({**row, "strategy": strategy})
        fences[strategy] = fence_stats(
            record["document"]
            for index in runs[strategy].values()
            for record in store.iter_records(index.collection)
        )
    scores = strategy_scores(rows)
    decision = decide(scores)
    env = {
        "experiment": "E2",
        "date": run_date,
        "git_commit": _git_commit(),
        "python": platform.python_version(),
        "embedding_model": embedding_config.model,
        "runs": ", ".join(
            f"{s}:{k}=run{i.run_id}" for s in STRATEGIES for k, i in sorted(runs[s].items())
        ),
        "top_k": ", ".join(str(k) for k in E2_KS),
        "questions": f"Q-ret={len(sets.ret)}",
        "unreviewed_questions": len(unreviewed(sets)),
        "decision": f"strategy={decision.strategy}, top_k={decision.top_k}",
    }
    paths = write_results(out_dir, "E2", rows, env)
    (out_dir / "E2" / "decision.md").write_text(
        decision_markdown(decision, scores, rows, fences, runs, run_date),
        encoding="utf-8",
        newline="\n",
    )
    return paths


# --- CLI ----------------------------------------------------------------------


def check(sets: QuestionSets) -> int:
    errors = v1_composition_errors(sets)
    pending = unreviewed(sets)
    print(f"질문셋: {sets.counts()}")
    for error in errors:
        print(f"구성 오류: {error}", file=sys.stderr)
    print(
        f"사람 검수 대기: {len(pending)}문항" + (" (eval-v1 태그 전 0이어야 함)" if pending else "")
    )
    return 1 if errors else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m src.eval.run", description="검색 평가 러너")
    parser.add_argument("--exp", nargs="+", choices=EXPERIMENTS, default=list(EXPERIMENTS))
    parser.add_argument(
        "--conditions", nargs="+", choices=E1_CONDITIONS, default=list(E1_CONDITIONS)
    )
    parser.add_argument("--k", nargs="+", type=int, default=list(DEFAULT_KS), dest="ks")
    parser.add_argument("--out-dir", type=Path, default=RESULTS_DIR)
    parser.add_argument("--check", action="store_true", help="질문셋 검증만 하고 끝낸다")
    return parser


def main(argv: Sequence[str] | None = None, settings: Settings | None = None) -> int:
    args = build_parser().parse_args(argv)
    sets = load_question_sets()
    if args.check:
        return check(sets)
    if v1_composition_errors(sets):
        return check(sets)
    if any(k < 1 for k in args.ks):
        print("--k 값은 1 이상이어야 합니다", file=sys.stderr)
        return 2
    settings = settings or Settings()
    try:
        for experiment in args.exp:
            if experiment == "E1":
                rows_path, summary_path = run_e1(
                    settings, sets, args.conditions, args.out_dir, sorted(set(args.ks))
                )
            else:
                rows_path, summary_path = run_e2(settings, sets, args.out_dir)
            print(f"{experiment}: {rows_path} · {summary_path}")
    except (RetrieverUnavailableError, StrategyRunsMissingError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except LookupError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

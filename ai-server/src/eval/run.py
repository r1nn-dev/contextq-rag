"""검색 평가 러너 — E1(버전 격리)·E2(청킹 전략) 결과 JSONL·요약 CSV (evaluation.md §3·§4).

    uv run python -m src.eval.run --exp E1 [--conditions N F C] [--out-dir ../eval/results]
    uv run python -m src.eval.run --check        # 질문셋 스키마·v1 구성·검수 상태만 확인

- 검색은 `Retriever` 계약(interfaces.md §4)으로만 한다. E1-C·E2는 서비스 Retriever를 쓰고,
  E1-N·E1-F는 실험용 병합 컬렉션 검색기를 쓴다(conditions.py).
- 서비스 Retriever(`ChromaRetriever`)는 버전 격리 검색 작업(R-4-1)에서 연결한다.
  그 전에는 E1-C·E2 요청이 `RetrieverUnavailableError`로 끝난다.
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
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.config.ingest_config import load_embedding_config
from src.config.settings import Settings
from src.domain.retrieval import RetrievedChunk, Retriever
from src.domain.tables import IndexPointer
from src.eval.conditions import (
    E1_CONDITIONS,
    Condition,
    MergedCollectionSearcher,
    build_merged_collection,
    embed_queries,
    merged_collection_name,
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
from src.ingest.store import ChromaVectorStore, VectorStore, collection_name

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
    """서비스 Retriever가 아직 연결되지 않음 (R-4-1)."""


def unavailable_service_retriever() -> Retriever:
    raise RetrieverUnavailableError(
        "서비스 Retriever는 버전 격리 검색 작업(R-4-1)에서 연결한다. "
        "지금은 E1을 --conditions N F 로만 실행할 수 있다."
    )


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
        emit(q.question_id, "Q-ret", q.source_key, chunks, gold_flags(chunks, q.gold.sections))
    for oq in oos:
        for source_key in VERSION_SOURCE_KEYS.values():
            chunks = searcher.retrieve(oq.query, source_key, top)
            emit(oq.question_id, "Q-oos", source_key, chunks, None)
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


def active_runs(session: Session) -> dict[str, int]:
    """평가 대상 소스의 ACTIVE run id (ai.index_pointers)."""
    pointers = session.scalars(
        select(IndexPointer).where(IndexPointer.source_key.in_(list(VERSION_SOURCE_KEYS.values())))
    ).all()
    found = {p.source_key: p.active_run_id for p in pointers}
    missing = sorted(set(VERSION_SOURCE_KEYS.values()) - set(found))
    if missing:
        raise LookupError(f"ACTIVE run이 없는 소스: {missing}")
    return found


@dataclass(frozen=True)
class E1Inputs:
    store: VectorStore
    runs: Mapping[str, int]
    embeddings: Mapping[str, Sequence[float]]
    service_retriever: Callable[[], Retriever]


def e1_searchers(inputs: E1Inputs, conditions: Sequence[Condition]) -> dict[str, Retriever]:
    """조건 코드 → 검색기. N·F가 있으면 병합 컬렉션을 만든다(있으면 재사용)."""
    searchers: dict[str, Retriever] = {}
    if "N" in conditions or "F" in conditions:
        name = merged_collection_name(inputs.runs)
        sources = {key: collection_name(key, run_id) for key, run_id in inputs.runs.items()}
        build_merged_collection(inputs.store, sources, name)
        for code in ("N", "F"):
            if code in conditions:
                searchers[f"E1-{code}"] = MergedCollectionSearcher(
                    inputs.store, name, inputs.embeddings, filter_by_source=code == "F"
                )
    if "C" in conditions:
        searchers["E1-C"] = inputs.service_retriever()
    return searchers


def run_e1(
    settings: Settings,
    sets: QuestionSets,
    conditions: Sequence[Condition],
    out_dir: Path,
    ks: Sequence[int],
    service_retriever: Callable[[], Retriever] = unavailable_service_retriever,
) -> tuple[Path, Path]:
    if "C" in conditions:
        service_retriever()  # 연결 전이면 비싼 준비(임베딩·병합) 전에 실패
    engine = create_engine(settings.database_url)
    try:
        with Session(engine) as session:
            runs = active_runs(session)
    finally:
        engine.dispose()
    store = ChromaVectorStore(settings.chroma_data_dir)
    embedding_config = load_embedding_config()
    queries = [q.query for q in sets.ret] + [q.query for q in sets.oos]
    embeddings: Mapping[str, Sequence[float]] = {}
    if "N" in conditions or "F" in conditions:
        embedder = OpenAIEmbeddingClient(settings.openai_api_key, embedding_config)
        embeddings = asyncio.run(embed_queries(embedder, queries))
    searchers = e1_searchers(E1Inputs(store, runs, embeddings, service_retriever), conditions)
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
        "active_runs": ", ".join(f"{k}=run{v}" for k, v in sorted(runs.items())),
        "conditions": ", ".join(searchers),
        "top_k": ", ".join(str(k) for k in ks),
        "questions": ", ".join(f"{k}={v}" for k, v in sets.counts().items()),
        "unreviewed_questions": len(unreviewed(sets)),
    }
    return write_results(out_dir, "E1", rows, env)


def run_e2() -> tuple[Path, Path]:
    raise RetrieverUnavailableError(
        "E2는 전략별 인덱스(R-7-3)와 서비스 Retriever(R-4-1)가 있어야 실행할 수 있다."
    )


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
                rows_path, summary_path = run_e2()
            print(f"{experiment}: {rows_path} · {summary_path}")
    except RetrieverUnavailableError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except LookupError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

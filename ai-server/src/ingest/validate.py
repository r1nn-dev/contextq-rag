"""VALIDATING 게이트 항목별 검사기 — 정책서 §4.4.

각 검사기는 `CheckResult`를 돌려준다. 게이트 실행·제한 시간·상태 전이는 파이프라인이 맡는다.
전처리 잔존물 중 "코드 펜스 내부 diff"와 "출력 셀"은 컬렉션만으로 확인할 수 없어,
Adapter 골든 테스트·실측과 노트북 직렬화(출력 셀을 넣지 않음)로 보장한다.
"""

import asyncio
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from src.config.ingest_config import SmokeQuestion
from src.ingest.chunking import MIN_CHUNK_CHARS, visible_chars
from src.ingest.embedder import EmbeddingClient
from src.ingest.metadata import REQUIRED_FIELDS
from src.ingest.store import VectorStore

DRIFT_TOLERANCE = 0.30  # 정책서 §4.4 청크 수 ±30%
VALIDATION_TIMEOUT_SECONDS = 600  # 정책서 §10.1 게이트 10분 제한
MAX_EXAMPLES = 20  # 리포트에 남길 위반 예시 수

# 닫는 `---`까지 있는 YAML 블록만 frontmatter로 본다 (수평선 + "Note:" 같은 본문 오탐 방지)
_FRONTMATTER = re.compile(r"\A---\n(?:[A-Za-z_][\w-]*:.*\n)+---(?:\n|\Z)")
_JS_BLOCK = re.compile(r"^\s*:::js\b", re.MULTILINE)
_MARKER = re.compile(r"^\s*:::", re.MULTILINE)  # 조건부 블록·admonition 마커 (제목 포함)
_FENCE_OPEN = re.compile(r"^\s*(`{3,}|~{3,})")


class ValidationTimeoutError(TimeoutError):
    """게이트가 제한 시간 안에 끝나지 않음 → FAILED(VALIDATION_TIMEOUT)."""


@dataclass(frozen=True)
class Deadline:
    at: float  # time.monotonic() 기준

    @classmethod
    def after(cls, seconds: float) -> "Deadline":
        return cls(time.monotonic() + seconds)

    def check(self) -> None:
        if time.monotonic() > self.at:
            raise ValidationTimeoutError("VALIDATION_TIMEOUT: 검증 게이트 제한 시간 초과")


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, **self.detail}


def check_chunk_count(chunk_count: int, previous: int | None, accept_drift: bool) -> CheckResult:
    """0 초과, 직전 ACTIVE 대비 ±30% 이내. 초과는 accept_drift로만 통과한다."""
    detail: dict[str, Any] = {"chunk_count": chunk_count, "prev_chunk_count": previous}
    if chunk_count <= 0:
        return CheckResult("chunk_count", False, {**detail, "reason": "청크 0건"})
    if previous:
        drift = (chunk_count - previous) / previous
        detail["drift"] = round(drift, 4)
        if abs(drift) > DRIFT_TOLERANCE:
            detail["accepted_by_flag"] = accept_drift
            return CheckResult("chunk_count", accept_drift, detail)
    return CheckResult("chunk_count", True, detail)


def _outside_fences(text: str) -> str:
    """펜스 밖 줄만 이어 붙인다 (잔존물 검사는 코드 안 문자열을 보지 않는다)."""
    kept: list[str] = []
    marker: str | None = None
    for line in text.split("\n"):
        if marker is None:
            match = _FENCE_OPEN.match(line)
            if match:
                marker = match.group(1)
                continue
            kept.append(line)
        else:
            stripped = line.strip()
            if stripped.startswith(marker[0] * len(marker)) and set(stripped) == {marker[0]}:
                marker = None
    return "\n".join(kept)


@dataclass
class _RecordStats:
    total: int = 0
    missing: dict[str, int] = field(default_factory=dict)
    missing_examples: list[str] = field(default_factory=list)
    residue: dict[str, int] = field(
        default_factory=lambda: {"frontmatter": 0, "js_block": 0, "marker": 0, "small_chunk": 0}
    )
    residue_examples: list[str] = field(default_factory=list)
    wrong_model: int = 0
    wrong_dim: int = 0
    embedding_examples: list[str] = field(default_factory=list)


def check_records(
    records: Iterable[dict[str, Any]],
    *,
    expected_model: str,
    expected_dim: int,
    deadline: Deadline,
) -> list[CheckResult]:
    """컬렉션을 한 번 순회하며 필수 메타데이터·전처리 잔존물·임베딩 모델/차원을 검사한다."""
    stats = _RecordStats()
    for record in records:
        stats.total += 1
        if stats.total % 500 == 0:
            deadline.check()
        record_id = str(record["id"])
        metadata: dict[str, Any] = record["metadata"]
        document: str = record["document"] or ""

        absent = [f for f in REQUIRED_FIELDS if metadata.get(f) in (None, "")]
        for name in absent:
            stats.missing[name] = stats.missing.get(name, 0) + 1
        if absent and len(stats.missing_examples) < MAX_EXAMPLES:
            stats.missing_examples.append(f"{record_id}: {', '.join(absent)}")

        prose = _outside_fences(document)
        found = {
            "frontmatter": bool(_FRONTMATTER.match(document.lstrip())),
            "js_block": bool(_JS_BLOCK.search(prose)),
            "marker": bool(_MARKER.search(prose)),
            "small_chunk": visible_chars(document) < MIN_CHUNK_CHARS,
        }
        for name, hit in found.items():
            if hit:
                stats.residue[name] += 1
        if any(found.values()) and len(stats.residue_examples) < MAX_EXAMPLES:
            stats.residue_examples.append(
                f"{metadata.get('file_path')}#L{metadata.get('line_start')}: "
                + ", ".join(k for k, v in found.items() if v)
            )

        model_ok = metadata.get("embedding_model") == expected_model
        dim_ok = len(record.get("embedding") or []) == expected_dim
        stats.wrong_model += not model_ok
        stats.wrong_dim += not dim_ok
        if (not model_ok or not dim_ok) and len(stats.embedding_examples) < MAX_EXAMPLES:
            stats.embedding_examples.append(record_id)

    return [
        CheckResult(
            "required_metadata",
            stats.total > 0 and not stats.missing,
            {"records": stats.total, "missing": stats.missing, "examples": stats.missing_examples},
        ),
        CheckResult(
            "preprocessing_residue",
            not any(stats.residue.values()),
            {
                "counts": stats.residue,
                "examples": stats.residue_examples,
                "not_in_gate": {
                    "code_fence_diff": "Adapter 골든 테스트·실측으로 보장",
                    "notebook_outputs": "직렬화 단계에서 출력 셀을 넣지 않음",
                },
            },
        ),
        CheckResult(
            "embedding_model_dim",
            stats.total > 0 and stats.wrong_model == 0 and stats.wrong_dim == 0,
            {
                "expected_model": expected_model,
                "expected_dim": expected_dim,
                "wrong_model": stats.wrong_model,
                "wrong_dim": stats.wrong_dim,
                "examples": stats.embedding_examples,
            },
        ),
    ]


def check_collection_metadata(
    metadata: dict[str, Any], *, expected_model: str, expected_dim: int
) -> CheckResult:
    ok = (
        metadata.get("embedding_model") == expected_model
        and metadata.get("embedding_dim") == expected_dim
        and metadata.get("hnsw:space") == "cosine"
    )
    return CheckResult("collection_metadata", ok, {"metadata": metadata})


def check_smoke(
    store: VectorStore,
    collection: str,
    embedder: EmbeddingClient,
    questions: list[SmokeQuestion],
    *,
    tau: float,
    top_k: int,
) -> CheckResult:
    """버전당 5문항: 기대 파일이 Top-K 안에 있고 top-1 similarity ≥ τ (5/5 통과)."""
    if not questions:
        return CheckResult("smoke", False, {"reason": "스모크 질문이 없습니다"})
    vectors = asyncio.run(embedder.embed([q.question for q in questions]))
    results = []
    for question, vector in zip(questions, vectors, strict=True):
        hits = store.query(collection, vector, top_k)
        files = [str(h.metadata.get("file_path")) for h in hits]
        top1 = hits[0].similarity if hits else 0.0
        passed = question.expected_file in files and top1 >= tau
        results.append(
            {
                "question": question.question,
                "expected_file": question.expected_file,
                "rank": files.index(question.expected_file) + 1
                if question.expected_file in files
                else None,
                "top1_similarity": round(top1, 4),
                "passed": passed,
            }
        )
    passed_count = sum(1 for r in results if r["passed"])
    return CheckResult(
        "smoke",
        passed_count == len(questions),
        {"tau": tau, "top_k": top_k, "passed": passed_count, "total": len(questions),
         "results": results},
    )  # fmt: skip

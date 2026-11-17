"""VALIDATING 게이트 검사기 — 정책서 §4.4."""

from pathlib import Path
from typing import Any

import pytest

from src.config.ingest_config import SmokeQuestion, load_smoke_config
from src.ingest.metadata import REQUIRED_FIELDS
from src.ingest.store import ChromaVectorStore
from src.ingest.validate import (
    Deadline,
    ValidationTimeoutError,
    check_chunk_count,
    check_collection_metadata,
    check_records,
    check_smoke,
)

BODY = "This chunk body is comfortably longer than fifty visible characters in total."


def _record(document: str = BODY, dim: int = 4, **overrides: Any) -> dict[str, Any]:
    metadata: dict[str, Any] = {name: "x" for name in REQUIRED_FIELDS}
    metadata.update({"embedding_model": "m", "file_path": "a.mdx", "line_start": 1})
    metadata.update(overrides)
    return {"id": "c1", "document": document, "metadata": metadata, "embedding": [0.1] * dim}


def _results(records: list[dict[str, Any]]) -> dict[str, Any]:
    checks = check_records(records, expected_model="m", expected_dim=4, deadline=Deadline.after(60))
    return {c.name: c for c in checks}


@pytest.mark.parametrize(
    ("count", "previous", "accept", "passed"),
    [
        (0, None, False, False),
        (100, None, False, True),
        (130, 100, False, True),
        (69, 100, False, False),
        (131, 100, False, False),
        (131, 100, True, True),
    ],
)
def test_chunk_count_drift(count: int, previous: int | None, accept: bool, passed: bool) -> None:
    assert check_chunk_count(count, previous, accept).passed is passed


def test_clean_records_pass() -> None:
    results = _results([_record()])
    assert all(c.passed for c in results.values())


def test_missing_metadata_fails() -> None:
    results = _results([_record(permalink="")])
    assert not results["required_metadata"].passed
    assert results["required_metadata"].detail["missing"] == {"permalink": 1}


@pytest.mark.parametrize(
    ("document", "residue"),
    [
        ("---\ntitle: Agents\n---\n" + BODY, "frontmatter"),
        (":::js\n" + BODY, "js_block"),
        (":::info Prerequisites\n" + BODY, "marker"),
        ("short", "small_chunk"),
    ],
)
def test_residue_detected(document: str, residue: str) -> None:
    result = _results([_record(document)])["preprocessing_residue"]
    assert not result.passed
    assert result.detail["counts"][residue] == 1


@pytest.mark.parametrize(
    "document",
    [
        "---\nNote: a horizontal rule followed by prose is not frontmatter at all here.",
        "```md\n:::js\n---\ntitle: x\n---\n```\n" + BODY,
    ],
)
def test_residue_ignores_prose_rules_and_fenced_text(document: str) -> None:
    assert _results([_record(document)])["preprocessing_residue"].passed


def test_embedding_model_and_dim_checked() -> None:
    results = _results([_record(dim=3), _record(embedding_model="other")])
    detail = results["embedding_model_dim"].detail
    assert (detail["wrong_dim"], detail["wrong_model"]) == (1, 1)
    assert not results["embedding_model_dim"].passed


def test_empty_collection_fails() -> None:
    results = _results([])
    assert not results["required_metadata"].passed
    assert not results["embedding_model_dim"].passed


def test_collection_metadata() -> None:
    ok = {"embedding_model": "m", "embedding_dim": 4, "hnsw:space": "cosine"}
    assert check_collection_metadata(ok, expected_model="m", expected_dim=4).passed
    assert not check_collection_metadata(
        {**ok, "hnsw:space": "l2"}, expected_model="m", expected_dim=4
    ).passed


def test_deadline() -> None:
    with pytest.raises(ValidationTimeoutError, match="VALIDATION_TIMEOUT"):
        Deadline.after(-1).check()


class _KeywordEmbedder:
    """질문·문서에 든 키워드로 같은 방향 벡터를 만든다 (검색 결과를 통제하기 위함)."""

    model = "m"
    dimensions = 3
    total_tokens = 0
    axes = {"tools": [1.0, 0.0, 0.0], "memory": [0.0, 1.0, 0.0]}

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [next((v for k, v in self.axes.items() if k in t), [0.0, 0.0, 1.0]) for t in texts]


@pytest.fixture()
def smoke_store(tmp_path: Path) -> ChromaVectorStore:
    store = ChromaVectorStore(tmp_path / "chroma")
    store.create_collection("s_run1", {})
    store.add(
        "s_run1",
        ids=["t", "m"],
        embeddings=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        documents=["tools", "memory"],
        metadatas=[{"file_path": "tools.mdx"}, {"file_path": "memory.mdx"}],
    )
    return store


def test_smoke_pass_and_fail(smoke_store: ChromaVectorStore) -> None:
    questions = [
        SmokeQuestion(question="how to use tools", expected_file="tools.mdx"),
        SmokeQuestion(question="add memory", expected_file="memory.mdx"),
    ]
    passed = check_smoke(smoke_store, "s_run1", _KeywordEmbedder(), questions, tau=0.3, top_k=1)
    assert passed.passed and passed.detail["passed"] == 2

    wrong = [SmokeQuestion(question="how to use tools", expected_file="memory.mdx")]
    failed = check_smoke(smoke_store, "s_run1", _KeywordEmbedder(), wrong, tau=0.3, top_k=1)
    assert not failed.passed
    assert failed.detail["results"][0]["rank"] is None


def test_smoke_tau_threshold(smoke_store: ChromaVectorStore) -> None:
    question = [SmokeQuestion(question="unrelated", expected_file="tools.mdx")]
    result = check_smoke(smoke_store, "s_run1", _KeywordEmbedder(), question, tau=0.3, top_k=2)
    assert not result.passed  # 기대 파일은 Top-2 안이지만 top-1 similarity 0 < τ


def test_smoke_config_has_five_questions_per_source() -> None:
    config = load_smoke_config()
    assert config.tau == 0.30 and config.top_k == 5
    assert {k: len(v) for k, v in config.sources.items()} == {
        "langchain_v03": 5,
        "langchain_v1x": 5,
    }

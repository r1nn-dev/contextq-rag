"""E1 비교 조건 — 실험용 병합 컬렉션과 N·F 검색기 (protocol.md 실험 E1)."""

from pathlib import Path

import pytest

from src.eval.conditions import (
    MergedCollectionSearcher,
    build_merged_collection,
    embed_queries,
    merged_collection_name,
)
from src.ingest.store import ChromaVectorStore
from tests.unit.conftest import FakeEmbedder

V03, V1X = "langchain_v03", "langchain_v1x"


def _meta(source_key: str, heading: str) -> dict[str, object]:
    return {
        "source_key": source_key,
        "file_path": f"{source_key}/doc.md",
        "heading_path": heading,
        "token_count": 10,
        "permalink": "https://example.invalid",
    }


@pytest.fixture()
def store(tmp_path: Path) -> ChromaVectorStore:
    store = ChromaVectorStore(tmp_path / "chroma", page_size=2)
    for source_key, vectors in {
        V03: [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        V1X: [[0.95, 0.05, 0.0], [0.0, 0.0, 1.0], [0.1, 0.9, 0.0]],
    }.items():
        name = f"{source_key}_run1"
        store.create_collection(name, {})
        store.add(
            name,
            ids=[f"{source_key}-{i}" for i in range(len(vectors))],
            embeddings=vectors,
            documents=[f"{source_key} {i}" for i in range(len(vectors))],
            metadatas=[_meta(source_key, f"Doc > S{i}") for i in range(len(vectors))],
        )
    return store


SOURCES = {V03: f"{V03}_run1", V1X: f"{V1X}_run1"}


def test_merged_collection_name_includes_sorted_runs() -> None:
    name = merged_collection_name({V1X: 3, V03: 1})

    assert name == "eval_e1_merged_langchain_v03_r1_langchain_v1x_r3"


def test_build_merged_collection_copies_all_records_and_reuses(store: ChromaVectorStore) -> None:
    name = merged_collection_name({V03: 1, V1X: 1})

    assert build_merged_collection(store, SOURCES, name) == 5
    assert build_merged_collection(store, SOURCES, name) == 5  # 재사용 (중복 추가 없음)
    record = next(r for r in store.iter_records(name) if r["id"] == f"{V1X}-1")
    assert record["metadata"]["heading_path"] == "Doc > S1"


def test_build_merged_collection_rebuilds_incomplete_copy(store: ChromaVectorStore) -> None:
    name = merged_collection_name({V03: 1, V1X: 1})
    store.create_collection(name, {})  # 중간에 끊긴 이전 시도

    assert build_merged_collection(store, SOURCES, name) == 5


def test_no_filter_mixes_sources_and_filter_isolates(store: ChromaVectorStore) -> None:
    name = merged_collection_name({V03: 1, V1X: 1})
    build_merged_collection(store, SOURCES, name)
    embeddings = {"q": [1.0, 0.0, 0.0]}
    n = MergedCollectionSearcher(store, name, embeddings, filter_by_source=False)
    f = MergedCollectionSearcher(store, name, embeddings, filter_by_source=True)

    mixed = n.retrieve("q", V1X, top_k=2)
    isolated = f.retrieve("q", V1X, top_k=2)

    assert [c["source_key"] for c in mixed] == [V03, V1X]  # 비격리: 다른 버전 청크가 1위
    assert {c["source_key"] for c in isolated} == {V1X}
    assert isolated[0]["file_path"] == f"{V1X}/doc.md"
    assert isolated[0]["token_count"] == 10
    assert isolated[0]["content"] == f"{V1X} 0"


async def test_embed_queries_deduplicates() -> None:
    embedder = FakeEmbedder(dimensions=4)

    result = await embed_queries(embedder, ["b", "a", "b"])

    assert sorted(result) == ["a", "b"]
    assert len(result["a"]) == 4

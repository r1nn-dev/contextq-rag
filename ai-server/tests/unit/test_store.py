"""Chroma 임베디드 저장소 — run 컬렉션 생성·저장·순회·삭제 (임시 디렉터리, OpenAI 호출 없음)."""

from pathlib import Path

import pytest

from src.ingest.store import ChromaVectorStore, CollectionExistsError, collection_name


@pytest.fixture()
def store(tmp_path: Path) -> ChromaVectorStore:
    return ChromaVectorStore(tmp_path / "chroma", page_size=2)


def test_collection_name_follows_policy() -> None:
    assert collection_name("langchain_v03", 12) == "langchain_v03_run12"


def test_create_add_count_and_iterate(store: ChromaVectorStore) -> None:
    name = collection_name("langchain_v1x", 1)
    store.create_collection(name, {"embedding_model": "m", "embedding_dim": 3})
    store.add(
        name,
        ids=["a", "b", "c"],
        embeddings=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        documents=["A", "B", "C"],
        metadatas=[{"i": 0}, {"i": 1}, {"i": 2}],
    )

    assert store.count(name) == 3
    meta = store.collection_metadata(name)
    assert meta["hnsw:space"] == "cosine"
    assert meta["embedding_dim"] == 3
    records = list(store.iter_records(name, include_embeddings=True))  # page_size=2 → 2페이지
    assert sorted(r["id"] for r in records) == ["a", "b", "c"]
    by_id = {r["id"]: r for r in records}
    assert by_id["b"]["document"] == "B"
    assert by_id["b"]["metadata"] == {"i": 1}
    assert by_id["b"]["embedding"] == pytest.approx([0.0, 1.0, 0.0])


def test_existing_collection_is_not_overwritten(store: ChromaVectorStore) -> None:
    name = collection_name("langchain_v1x", 2)
    store.create_collection(name, {})
    with pytest.raises(CollectionExistsError):
        store.create_collection(name, {})


def test_delete_collection_is_idempotent(store: ChromaVectorStore) -> None:
    name = collection_name("langchain_v1x", 3)
    store.create_collection(name, {})
    store.delete_collection(name)
    store.delete_collection(name)
    assert not store.has_collection(name)


def test_query_returns_documents_and_applies_metadata_filter(store: ChromaVectorStore) -> None:
    name = "eval_query_test"
    store.create_collection(name, {})
    store.add(
        name,
        ids=["a", "b"],
        embeddings=[[1.0, 0.0, 0.0], [0.9, 0.1, 0.0]],
        documents=["A", "B"],
        metadatas=[{"source_key": "s1"}, {"source_key": "s2"}],
    )

    hits = store.query(name, [1.0, 0.0, 0.0], k=2)
    filtered = store.query(name, [1.0, 0.0, 0.0], k=2, where={"source_key": "s2"})

    assert [h.chunk_id for h in hits] == ["a", "b"]
    assert hits[0].document == "A"
    assert hits[0].similarity == pytest.approx(1.0)
    assert [h.chunk_id for h in filtered] == ["b"]

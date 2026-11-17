"""벡터 저장소 경계와 Chroma 임베디드 구현 — ADR-002, ADR-004, 정책서 §4.1.

- run과 컬렉션은 1:1이다. 이름은 `{source_key}_run{ingest_run_id}`로만 만든다 (상수 금지).
- 거리 함수는 cosine 고정 (`hnsw:space = cosine`, similarity = 1 − distance).
- 서버 모드로 바꿀 때는 `VectorStore` 구현만 바꾼다 (기획서 결정 3).
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import chromadb
from chromadb.config import Settings as ChromaSettings

DISTANCE = "cosine"


def collection_name(source_key: str, run_id: int) -> str:
    return f"{source_key}_run{run_id}"


class CollectionExistsError(RuntimeError):
    """같은 run의 컬렉션이 이미 있다 — 재수집은 새 run이어야 한다."""


class VectorStore(Protocol):
    def create_collection(self, name: str, metadata: dict[str, Any]) -> None: ...

    def add(
        self,
        name: str,
        ids: Sequence[str],
        embeddings: Sequence[Sequence[float]],
        documents: Sequence[str],
        metadatas: Sequence[dict[str, Any]],
    ) -> None: ...

    def count(self, name: str) -> int: ...

    def collection_metadata(self, name: str) -> dict[str, Any]: ...

    def iter_records(
        self, name: str, *, include_embeddings: bool = False
    ) -> Iterator[dict[str, Any]]:
        """{"id", "document", "metadata"[, "embedding"]}를 순회한다 (검증 게이트용)."""
        ...

    def delete_collection(self, name: str) -> None: ...

    def has_collection(self, name: str) -> bool: ...

    def query(self, name: str, embedding: Sequence[float], k: int) -> list[QueryHit]:
        """similarity 내림차순 Top-k (similarity = 1 − cosine distance)."""
        ...


@dataclass(frozen=True)
class QueryHit:
    chunk_id: str
    similarity: float
    metadata: dict[str, Any]


class ChromaVectorStore:
    """Chroma 임베디드(PersistentClient). 임베딩은 항상 호출자가 계산해 넘긴다."""

    def __init__(self, path: Path, *, page_size: int = 1000) -> None:
        path.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=str(path), settings=ChromaSettings(anonymized_telemetry=False)
        )
        self.page_size = page_size

    def has_collection(self, name: str) -> bool:
        return name in {c.name for c in self.client.list_collections()}

    def create_collection(self, name: str, metadata: dict[str, Any]) -> None:
        if self.has_collection(name):
            raise CollectionExistsError(f"컬렉션이 이미 있습니다: {name}")
        self.client.create_collection(
            name=name,
            metadata={**metadata, "hnsw:space": DISTANCE},
            embedding_function=None,
        )

    def add(
        self,
        name: str,
        ids: Sequence[str],
        embeddings: Sequence[Sequence[float]],
        documents: Sequence[str],
        metadatas: Sequence[dict[str, Any]],
    ) -> None:
        collection = self.client.get_collection(name, embedding_function=None)
        batch = self.client.get_max_batch_size()
        for start in range(0, len(ids), batch):
            end = start + batch
            vectors: list[Sequence[float]] = [list(e) for e in embeddings[start:end]]
            collection.add(
                ids=list(ids[start:end]),
                embeddings=vectors,
                documents=list(documents[start:end]),
                metadatas=[dict(m) for m in metadatas[start:end]],
            )

    def count(self, name: str) -> int:
        return self.client.get_collection(name, embedding_function=None).count()

    def collection_metadata(self, name: str) -> dict[str, Any]:
        return dict(self.client.get_collection(name, embedding_function=None).metadata or {})

    def iter_records(
        self, name: str, *, include_embeddings: bool = False
    ) -> Iterator[dict[str, Any]]:
        collection = self.client.get_collection(name, embedding_function=None)
        include: list[Any] = ["documents", "metadatas"]
        if include_embeddings:
            include.append("embeddings")
        offset = 0
        while True:
            page = collection.get(limit=self.page_size, offset=offset, include=include)
            ids = page["ids"]
            if not ids:
                return
            for i, record_id in enumerate(ids):
                record: dict[str, Any] = {
                    "id": record_id,
                    "document": (page["documents"] or [])[i],
                    "metadata": dict((page["metadatas"] or [])[i] or {}),
                }
                if include_embeddings:
                    # Chroma는 임베딩을 numpy 배열로 돌려준다 (`or []` 진리값 평가 불가)
                    embeddings = page["embeddings"]
                    record["embedding"] = [float(v) for v in embeddings[i]]  # type: ignore[index]
                yield record
            offset += len(ids)

    def delete_collection(self, name: str) -> None:
        if self.has_collection(name):
            self.client.delete_collection(name)

    def query(self, name: str, embedding: Sequence[float], k: int) -> list[QueryHit]:
        collection = self.client.get_collection(name, embedding_function=None)
        vector: list[Sequence[float]] = [list(embedding)]
        result = collection.query(
            query_embeddings=vector, n_results=k, include=["metadatas", "distances"]
        )
        ids = result["ids"][0]
        distances = (result["distances"] or [[]])[0]
        metadatas = (result["metadatas"] or [[]])[0]
        return [
            QueryHit(chunk_id, 1.0 - float(distance), dict(metadata or {}))
            for chunk_id, distance, metadata in zip(ids, distances, metadatas, strict=True)
        ]

"""`VectorStore` 프로토콜의 인메모리 테스트 대역 — 코사인 유사도 + 메타데이터 등가 필터.

Chroma 1.5.9는 Windows에서 같은 프로세스에 작은 컬렉션을 여러 개 만들면, 먼저 만든 컬렉션을
뒤늦게 읽을 때 HNSW 세그먼트를 찾지 못해 간헐 실패한다(#145, Linux에서는 재현되지 않음).
병합·복사·필터 검색 같은 우리 로직을 보는 테스트는 이 대역을 쓴다. Chroma 자체의 저장·필터
동작은 `tests/unit/test_store.py`가 단일 컬렉션으로 검증한다.
"""

import math
from collections.abc import Iterator, Sequence
from typing import Any

from src.ingest.store import CollectionExistsError, QueryHit


class MemoryVectorStore:
    def __init__(self, *, page_size: int = 1000) -> None:
        self.page_size = page_size  # ChromaVectorStore와 인자를 맞춘다(순회는 한 번에 한다)
        self.collections: dict[str, dict[str, Any]] = {}

    def has_collection(self, name: str) -> bool:
        return name in self.collections

    def create_collection(self, name: str, metadata: dict[str, Any]) -> None:
        if name in self.collections:
            raise CollectionExistsError(f"컬렉션이 이미 있습니다: {name}")
        self.collections[name] = {"metadata": dict(metadata), "records": {}}

    def add(
        self,
        name: str,
        ids: Sequence[str],
        embeddings: Sequence[Sequence[float]],
        documents: Sequence[str],
        metadatas: Sequence[dict[str, Any]],
    ) -> None:
        records = self.collections[name]["records"]
        for record_id, embedding, document, metadata in zip(
            ids, embeddings, documents, metadatas, strict=True
        ):
            records[record_id] = {
                "id": record_id,
                "embedding": [float(v) for v in embedding],
                "document": document,
                "metadata": dict(metadata),
            }

    def count(self, name: str) -> int:
        return len(self.collections[name]["records"])

    def collection_metadata(self, name: str) -> dict[str, Any]:
        return dict(self.collections[name]["metadata"])

    def iter_records(
        self, name: str, *, include_embeddings: bool = False
    ) -> Iterator[dict[str, Any]]:
        for record in list(self.collections[name]["records"].values()):
            row = {
                "id": record["id"],
                "document": record["document"],
                "metadata": dict(record["metadata"]),
            }
            if include_embeddings:
                row["embedding"] = list(record["embedding"])
            yield row

    def delete_collection(self, name: str) -> None:
        self.collections.pop(name, None)

    def query(
        self,
        name: str,
        embedding: Sequence[float],
        k: int,
        where: dict[str, Any] | None = None,
    ) -> list[QueryHit]:
        candidates = [
            r
            for r in self.collections[name]["records"].values()
            if not where or all(r["metadata"].get(key) == value for key, value in where.items())
        ]
        ranked = sorted(candidates, key=lambda r: (-_cosine(embedding, r["embedding"]), r["id"]))
        scored = ranked[:k]
        return [
            QueryHit(
                r["id"], _cosine(embedding, r["embedding"]), dict(r["metadata"]), r["document"]
            )
            for r in scored
        ]


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return sum(x * y for x, y in zip(a, b, strict=True)) / norm if norm else 0.0

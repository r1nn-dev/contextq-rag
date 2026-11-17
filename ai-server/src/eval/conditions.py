"""E1 비교 조건 — protocol.md 실험 E1 (E1-N 비격리 · E1-F 필터 · E1-C 컬렉션 분리).

- E1-N·E1-F는 두 소스 ACTIVE 컬렉션을 합친 **실험용 병합 컬렉션**에서 검색한다.
  운영 경로(서비스 Retriever)에는 넣지 않는다 (ADR-004 컬렉션 격리 유지).
- E1-C는 운영 방식 그대로 서비스 `ChromaRetriever`를 쓴다 → 러너가 만든다.
- 쿼리 임베딩은 질문셋 전체를 한 번에 계산해 두고 조건마다 재사용한다(비용·결정성).
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from src.domain.retrieval import RetrievedChunk
from src.ingest.embedder import EmbeddingClient, EmbeddingError
from src.ingest.store import VectorStore
from src.retrieval.search import to_retrieved_chunk

Condition = Literal["N", "F", "C"]
E1_CONDITIONS: tuple[Condition, ...] = ("N", "F", "C")
MERGED_PREFIX = "eval_e1_merged"
_COPY_BATCH = 500


def merged_collection_name(active_runs: Mapping[str, int]) -> str:
    """`eval_e1_merged_{source}_r{run}_…` — run이 바뀌면 이름도 바뀌어 섞이지 않는다."""
    parts = [f"{source_key}_r{run_id}" for source_key, run_id in sorted(active_runs.items())]
    return "_".join([MERGED_PREFIX, *parts])


def build_merged_collection(store: VectorStore, sources: Mapping[str, str], name: str) -> int:
    """소스별 컬렉션 레코드(임베딩 포함)를 `name` 하나로 복사한다. 이미 같은 개수면 재사용.

    Args:
        sources: source_key → ACTIVE 컬렉션 이름
    Returns:
        병합 컬렉션 레코드 수
    """
    expected = sum(store.count(collection) for collection in sources.values())
    if store.has_collection(name):
        if store.count(name) == expected:
            return expected
        store.delete_collection(name)  # 이전 시도가 중간에 끊긴 경우
    store.create_collection(name, {"purpose": "eval E1-N/E1-F", "sources": ",".join(sources)})
    for collection in sources.values():
        _copy(store, collection, name)
    return store.count(name)


def _copy(store: VectorStore, source: str, target: str) -> None:
    batch: list[dict[str, Any]] = []
    for record in store.iter_records(source, include_embeddings=True):
        batch.append(record)
        if len(batch) >= _COPY_BATCH:
            _flush(store, target, batch)
    _flush(store, target, batch)


def _flush(store: VectorStore, target: str, batch: list[dict[str, Any]]) -> None:
    if not batch:
        return
    store.add(
        target,
        ids=[r["id"] for r in batch],
        embeddings=[r["embedding"] for r in batch],
        documents=[r["document"] for r in batch],
        metadatas=[r["metadata"] for r in batch],
    )
    batch.clear()


async def embed_queries(
    embedder: EmbeddingClient, queries: Iterable[str]
) -> dict[str, list[float]]:
    """중복을 뺀 질의 텍스트 → 임베딩. 입력 순서와 무관하게 같은 결과를 낸다."""
    unique = sorted(set(queries))
    vectors = await embedder.embed(unique) if unique else []
    return dict(zip(unique, vectors, strict=True))


@dataclass(frozen=True)
class MergedCollectionSearcher:
    """E1-N(`filter_by_source=False`)·E1-F(`True`) 실험용 검색기. `Retriever` 계약을 따른다."""

    store: VectorStore
    collection: str
    embeddings: Mapping[str, Sequence[float]]
    filter_by_source: bool

    def retrieve(self, query: str, source_key: str, top_k: int = 5) -> list[RetrievedChunk]:
        where = {"source_key": source_key} if self.filter_by_source else None
        hits = self.store.query(self.collection, self.embeddings[query], top_k, where=where)
        return [to_retrieved_chunk(hit) for hit in hits]


@dataclass(frozen=True)
class PrecomputedQueryEmbedder:
    """미리 계산한 질의 임베딩을 돌려주는 `QueryEmbedder` — E1-C가 N·F와 같은 벡터를 쓴다."""

    embeddings: Mapping[str, Sequence[float]]
    model: str

    def embed_query(self, text: str) -> list[float]:
        try:
            return list(self.embeddings[text])
        except KeyError:
            raise EmbeddingError(f"미리 계산하지 않은 질의입니다: {text[:40]!r}") from None

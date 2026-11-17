"""버전 격리 검색 — ADR-004, 정책서 §5.3, interfaces.md §4 `Retriever`.

1차 격리: 요청 소스의 ACTIVE run 컬렉션 하나만 지정해 검색한다. `where` 필터는 쓰지 않는다.
요청은 시작할 때 확정한 `ActiveIndex`로 끝까지 검색한다 (`search(index=...)`).
"""

import time
from collections.abc import Callable
from dataclasses import dataclass

from src.domain.retrieval import RetrievedChunk
from src.ingest.store import QueryHit, VectorStore
from src.retrieval.embedding import QueryEmbedder
from src.retrieval.errors import IndexNotActiveError
from src.retrieval.pointers import ActiveIndex, PointerSource

MAX_TOP_K = 20  # interfaces.md §6.1 입력 제약 1 ≤ top_k ≤ 20


def to_retrieved_chunk(hit: QueryHit) -> RetrievedChunk:
    """Chroma 결과 1건 → 검색 계약 (interfaces.md §2.1)."""
    meta = hit.metadata
    return RetrievedChunk(
        chunk_id=hit.chunk_id,
        content=hit.document,
        permalink=str(meta.get("permalink", "")),
        source_key=str(meta["source_key"]),
        file_path=str(meta["file_path"]),
        heading_path=str(meta["heading_path"]),
        token_count=int(meta.get("token_count", 0)),
        site_url=str(meta.get("site_url", "")),
        similarity=hit.similarity,
    )


@dataclass(frozen=True)
class RetrievalResult:
    index: ActiveIndex  # 검색한 run 스냅샷 (meta·메시지 저장의 원천)
    chunks: list[RetrievedChunk]  # similarity 내림차순
    embed_ms: int
    retrieve_ms: int  # 벡터 검색 + 결과 검증 (임베딩 제외)


def _elapsed_ms(start: float, end: float) -> int:
    return max(0, round((end - start) * 1000))


class ChromaRetriever:
    """서비스 검색기. 평가 러너(E1-C)도 같은 객체를 쓴다 ("실험한 시스템 = 배포한 시스템")."""

    def __init__(
        self,
        store: VectorStore,
        pointers: PointerSource,
        embedder: QueryEmbedder,
        *,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.store = store
        self.pointers = pointers
        self.embedder = embedder
        self._clock = clock

    def resolve(self, source_key: str) -> ActiveIndex:
        """요청 시작 시 검색할 run을 확정한다 (소스·포인터 오류는 여기서 난다)."""
        return self.pointers.get(source_key)

    def retrieve(self, query: str, source_key: str, top_k: int = 5) -> list[RetrievedChunk]:
        """`Retriever` 계약 — similarity 내림차순, 결과가 없으면 빈 리스트."""
        return self.search(query, source_key, top_k).chunks

    def search(
        self,
        query: str,
        source_key: str,
        top_k: int = 5,
        *,
        index: ActiveIndex | None = None,
    ) -> RetrievalResult:
        if not query.strip():
            raise ValueError("query는 비어 있을 수 없습니다")
        if not 1 <= top_k <= MAX_TOP_K:
            raise ValueError(f"top_k는 1 이상 {MAX_TOP_K} 이하여야 합니다: {top_k}")
        index = index or self.resolve(source_key)
        if index.source_key != source_key:
            raise ValueError(f"확정한 run의 소스({index.source_key})와 요청 소스가 다릅니다")
        self._check_collection(index)

        t0 = self._clock()
        vector = self.embedder.embed_query(query)
        t1 = self._clock()
        hits = self.store.query(index.collection, vector, top_k)
        chunks = [to_retrieved_chunk(hit) for hit in hits]
        chunks.sort(key=lambda c: c["similarity"], reverse=True)
        t2 = self._clock()
        return RetrievalResult(index, chunks, _elapsed_ms(t0, t1), _elapsed_ms(t1, t2))

    def _check_collection(self, index: ActiveIndex) -> None:
        if not self.store.has_collection(index.collection):
            raise IndexNotActiveError(
                f"{index.source_key} ACTIVE run {index.run_id}의 컬렉션이 없습니다 "
                "(스냅샷 복원 필요)"
            )

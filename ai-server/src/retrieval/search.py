"""버전 격리 검색 — ADR-004, 정책서 §5.3, interfaces.md §4 `Retriever`.

1차 격리: 요청 소스의 ACTIVE run 컬렉션 하나만 지정해 검색한다. `where` 필터는 쓰지 않는다.
2차 검증(INV-02): 결과 청크의 `source_key`·`version`·`ingest_run_id`가 확정한 run과 다르면
폐기하고 ERROR 로그를 남긴다. 필터로 미리 걸러 내면 이 방어가 동작했는지 알 수 없다.
INV-03: 컬렉션·청크의 임베딩 모델이 질의 임베딩 모델과 다르면 검색을 거부한다.
요청은 시작할 때 확정한 `ActiveIndex`로 끝까지 검색한다 (`search(index=...)`).
"""

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from src.domain.retrieval import RetrievedChunk
from src.ingest.store import QueryHit, VectorStore
from src.retrieval.embedding import QueryEmbedder
from src.retrieval.errors import EmbeddingModelMismatchError, IndexNotActiveError
from src.retrieval.pointers import ActiveIndex, PointerSource

MAX_TOP_K = 20  # interfaces.md §6.1 입력 제약 1 ≤ top_k ≤ 20
_ISOLATION_FIELDS = ("source_key", "version", "ingest_run_id")

logger = logging.getLogger(__name__)


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
    discarded: int = 0  # INV-02로 폐기한 청크 수 (정상이면 0)


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
        self._checked: set[str] = set()  # INV-03 검사를 마친 컬렉션
        self._lock = threading.Lock()

    def resolve(self, source_key: str) -> ActiveIndex:
        """요청 시작 시 검색할 run을 확정한다 (소스·포인터 오류는 여기서 난다)."""
        return self.pointers.get(source_key)

    def prepare(self, source_key: str) -> ActiveIndex:
        """스트림 시작 전 확인 — run 확정 + 컬렉션 존재·임베딩 모델(INV-03).

        여기서 나는 오류는 HTTP 상태로 응답할 수 있다(200 전). 모두 캐시된 값이라 빠르다.
        """
        index = self.resolve(source_key)
        self._check_collection(index)
        return index

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
        kept = [hit for hit in hits if self._verify(index, hit)]
        chunks = [to_retrieved_chunk(hit) for hit in kept]
        chunks.sort(key=lambda c: c["similarity"], reverse=True)
        t2 = self._clock()
        return RetrievalResult(
            index, chunks, _elapsed_ms(t0, t1), _elapsed_ms(t1, t2), len(hits) - len(kept)
        )

    def _check_collection(self, index: ActiveIndex) -> None:
        """컬렉션 존재와 임베딩 모델(INV-03)을 컬렉션마다 한 번 확인한다."""
        name = index.collection
        with self._lock:
            if name in self._checked:
                return
        if not self.store.has_collection(name):
            raise IndexNotActiveError(
                f"{index.source_key} ACTIVE run {index.run_id}의 컬렉션이 없습니다 "
                "(스냅샷 복원 필요)"
            )
        model = self.store.collection_metadata(name).get("embedding_model")
        self._check_model(name, model)
        with self._lock:
            self._checked.add(name)

    def _check_model(self, where: str, model: object) -> None:
        if model != self.embedder.model:
            raise EmbeddingModelMismatchError(
                f"INV-03: {where} 임베딩 모델 {model!r} ≠ 질의 임베딩 모델 {self.embedder.model!r}"
            )

    def _verify(self, index: ActiveIndex, hit: QueryHit) -> bool:
        """INV-02 2차 검증. 다른 소스·버전·run 청크는 폐기한다(False)."""
        meta = hit.metadata
        self._check_model(f"청크 {hit.chunk_id}", meta.get("embedding_model"))
        expected = {
            "source_key": index.source_key,
            "version": index.version,
            "ingest_run_id": str(index.run_id),
        }
        actual = {field: str(meta.get(field)) for field in _ISOLATION_FIELDS}
        if actual == expected:
            return True
        logger.error(
            "retrieval_chunk_discarded",
            extra={
                "event": "retrieval_chunk_discarded",
                "invariant": "INV-02",
                "collection": index.collection,
                "chunk_id": hit.chunk_id,
                "expected": expected,
                "actual": actual,
            },
        )
        return False

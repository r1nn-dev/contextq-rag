"""검색 계약 — interfaces.md §2.1 `RetrievedChunk` · §4 `Retriever`.

서비스 검색(`ChromaRetriever`)과 평가 러너가 같은 계약을 쓴다
("실험한 시스템 = 배포한 시스템", protocol.md).
"""

from typing import Protocol, TypedDict


class RetrievedChunk(TypedDict):
    chunk_id: str
    content: str
    permalink: str
    source_key: str
    file_path: str
    heading_path: str
    token_count: int
    site_url: str
    similarity: float  # 0.0~1.0, 높을수록 관련성 높음


class Retriever(Protocol):
    def retrieve(self, query: str, source_key: str, top_k: int = 5) -> list[RetrievedChunk]:
        """similarity 내림차순 Top-k. 결과가 없으면 빈 리스트."""
        ...

"""질의 임베딩 — 정책서 §2.1 "OpenAI 임베딩 호출 5초, 재시도 1회", INV-03.

검색(`Retriever`)은 동기 계약이므로 동기 OpenAI 클라이언트를 쓴다(interfaces.md §4).
서버는 검색 전체를 스레드에서 실행해 이벤트 루프를 막지 않는다.
"""

from typing import Any, Protocol

import openai

from src.config.ingest_config import EmbeddingConfig
from src.ingest.embedder import EmbeddingError


class QueryEmbedder(Protocol):
    model: str  # INV-03 비교 기준

    def embed_query(self, text: str) -> list[float]: ...


class OpenAIQueryEmbedder:
    def __init__(self, api_key: str, config: EmbeddingConfig, client: Any = None) -> None:
        if client is None and not api_key:
            raise EmbeddingError("OPENAI_API_KEY가 설정되지 않아 질의를 임베딩할 수 없습니다")
        self.model = config.model
        self.dimensions = config.dimensions
        self.client = client or openai.OpenAI(
            api_key=api_key,
            timeout=config.query_timeout_seconds,
            max_retries=config.query_max_retries,
        )

    def embed_query(self, text: str) -> list[float]:
        if not text.strip():
            raise EmbeddingError("빈 질의는 임베딩하지 않습니다")
        try:
            response = self.client.embeddings.create(model=self.model, input=[text])
        except openai.OpenAIError as exc:
            raise EmbeddingError(f"질의 임베딩 실패: {type(exc).__name__}: {exc}") from exc
        if len(response.data) != 1:
            raise EmbeddingError(f"반환 벡터 수 불일치: 입력 1, 반환 {len(response.data)}")
        vector = list(response.data[0].embedding)
        if len(vector) != self.dimensions:
            raise EmbeddingError(f"임베딩 차원 불일치: 기대 {self.dimensions}, 실제 {len(vector)}")
        return vector

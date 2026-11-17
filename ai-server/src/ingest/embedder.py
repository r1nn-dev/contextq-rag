"""임베딩 클라이언트 — interfaces.md §4 `EmbeddingClient`, 정책서 §4.4 (차원·모델 일치).

반환 벡터 수·순서·차원이 입력과 맞지 않으면 `EmbeddingError`다.
토큰 사용량을 누적해 run의 `embedding_tokens`·`embedding_cost_usd`에 기록한다.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Protocol

import openai

from src.config.ingest_config import EmbeddingConfig


class EmbeddingError(Exception):
    """임베딩 API 호출 실패 또는 반환 벡터 불일치 (interfaces.md §5)."""


class EmbeddingClient(Protocol):
    model: str
    dimensions: int
    total_tokens: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


def embedding_cost_usd(tokens: int, price_per_1m_tokens: float) -> Decimal:
    """토큰 수 → 달러 (DB 컬럼 DECIMAL(8,6))."""
    cost = Decimal(tokens) * Decimal(str(price_per_1m_tokens)) / Decimal(1_000_000)
    return cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


class OpenAIEmbeddingClient:
    def __init__(self, api_key: str, config: EmbeddingConfig, client: Any = None) -> None:
        if client is None and not api_key:
            raise EmbeddingError("OPENAI_API_KEY가 설정되지 않아 임베딩을 호출할 수 없습니다")
        self.model = config.model
        self.dimensions = config.dimensions
        self.batch_size = config.batch_size
        self.total_tokens = 0
        self.client = client or openai.AsyncOpenAI(
            api_key=api_key, timeout=config.timeout_seconds, max_retries=config.max_retries
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts or any(not text.strip() for text in texts):
            raise EmbeddingError("빈 입력은 임베딩하지 않습니다")
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            try:
                response = await self.client.embeddings.create(model=self.model, input=batch)
            except openai.OpenAIError as exc:
                raise EmbeddingError(f"임베딩 API 호출 실패: {type(exc).__name__}: {exc}") from exc
            data = sorted(response.data, key=lambda item: item.index)
            if len(data) != len(batch):
                raise EmbeddingError(f"반환 벡터 수 불일치: 입력 {len(batch)}, 반환 {len(data)}")
            for item in data:
                if len(item.embedding) != self.dimensions:
                    raise EmbeddingError(
                        f"임베딩 차원 불일치: 기대 {self.dimensions}, 실제 {len(item.embedding)}"
                    )
                vectors.append(list(item.embedding))
            self.total_tokens += int(response.usage.total_tokens)
        return vectors

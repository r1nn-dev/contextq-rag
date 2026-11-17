"""OpenAI 임베딩 클라이언트 — 가짜 SDK 클라이언트로 배치·순서·차원·비용 확인 (API 호출 없음)."""

import os
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import openai
import pytest

from src.config.ingest_config import EmbeddingConfig, load_embedding_config
from src.ingest.embedder import EmbeddingError, OpenAIEmbeddingClient, embedding_cost_usd

CONFIG = EmbeddingConfig(
    model="text-embedding-3-small",
    dimensions=3,
    batch_size=2,
    timeout_seconds=1,
    max_retries=0,
    price_per_1m_tokens_usd=0.02,
    query_timeout_seconds=1,
    query_max_retries=0,
)


class _FakeEmbeddings:
    def __init__(self, *, dims: int = 3, drop: bool = False, error: Exception | None = None):
        self.calls: list[list[str]] = []
        self.dims, self.drop, self.error = dims, drop, error

    async def create(self, *, model: str, input: list[str]) -> Any:
        if self.error:
            raise self.error
        self.calls.append(input)
        items = [
            SimpleNamespace(index=i, embedding=[float(len(t))] * self.dims)
            for i, t in enumerate(input)
        ]
        items.reverse()  # 순서가 섞여 와도 index로 정렬해야 한다
        if self.drop:
            items = items[1:]
        return SimpleNamespace(data=items, usage=SimpleNamespace(total_tokens=10 * len(input)))


def _client(embeddings: _FakeEmbeddings) -> OpenAIEmbeddingClient:
    return OpenAIEmbeddingClient("", CONFIG, client=SimpleNamespace(embeddings=embeddings))


async def test_batches_preserve_order_and_count_tokens() -> None:
    fake = _FakeEmbeddings()
    client = _client(fake)
    vectors = await client.embed(["a", "bb", "ccc"])

    assert fake.calls == [["a", "bb"], ["ccc"]]
    assert vectors == [[1.0] * 3, [2.0] * 3, [3.0] * 3]
    assert client.total_tokens == 30


@pytest.mark.parametrize(
    ("fake", "message"),
    [
        (_FakeEmbeddings(drop=True), "반환 벡터 수"),
        (_FakeEmbeddings(dims=4), "차원"),
        (_FakeEmbeddings(error=openai.APIConnectionError(request=None)), "API 호출 실패"),  # type: ignore[arg-type]
    ],
)
async def test_mismatch_and_api_errors(fake: _FakeEmbeddings, message: str) -> None:
    with pytest.raises(EmbeddingError, match=message):
        await _client(fake).embed(["a", "b"])


@pytest.mark.parametrize("texts", [[], ["ok", "  "]])
async def test_empty_input_rejected(texts: list[str]) -> None:
    with pytest.raises(EmbeddingError):
        await _client(_FakeEmbeddings()).embed(texts)


def test_missing_api_key_fails_before_any_call() -> None:
    with pytest.raises(EmbeddingError, match="OPENAI_API_KEY"):
        OpenAIEmbeddingClient("", CONFIG)


def test_cost() -> None:
    assert embedding_cost_usd(646_044, 0.02) == Decimal("0.012921")
    assert embedding_cost_usd(0, 0.02) == Decimal("0.000000")


def test_embedding_config() -> None:
    config = load_embedding_config()
    assert (config.model, config.dimensions) == ("text-embedding-3-small", 1536)


@pytest.mark.llm
async def test_real_openai_embedding() -> None:
    """실제 API 호출 — 비밀값이 필요하므로 별도 터미널에서 `pytest -m llm`으로만 실행한다."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY 없음")
    client = OpenAIEmbeddingClient(api_key, load_embedding_config())
    vectors = await client.embed(["LangChain agents call tools in a loop."])
    assert len(vectors) == 1 and len(vectors[0]) == 1536
    assert client.total_tokens > 0

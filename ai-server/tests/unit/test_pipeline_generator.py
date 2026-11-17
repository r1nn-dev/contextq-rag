"""단일 모드 OpenAI 스트리밍 생성기 — 가짜 스트림 (정책서 §5.5·§2.1, rag-pipeline.md §3.6)."""

import asyncio
from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any

import openai
import pytest

from src.config.rag_config import load_llm_config
from src.domain.retrieval import RetrievedChunk
from src.pipeline.generator import LLMCallError, OpenAIAnswerGenerator
from src.pipeline.prompts import PromptNotFoundError

MODEL = "gpt-4o-mini-2024-07-18"


def piece(content: str | None = None, finish: str | None = None, role: str | None = None) -> Any:
    delta = SimpleNamespace(content=content, role=role)
    return SimpleNamespace(
        model=MODEL, usage=None, choices=[SimpleNamespace(delta=delta, finish_reason=finish)]
    )


def usage_piece(prompt: int, completion: int) -> Any:
    usage = SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion)
    return SimpleNamespace(model=MODEL, usage=usage, choices=[])


class FakeStream:
    def __init__(self, pieces: Sequence[Any], *, delay: float = 0, fail_at: int | None = None):
        self.pieces = list(pieces)
        self.delay = delay
        self.fail_at = fail_at
        self.closed = False
        self.i = 0

    def __aiter__(self) -> "FakeStream":
        return self

    async def __anext__(self) -> Any:
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail_at is not None and self.i == self.fail_at:
            raise openai.APIConnectionError(request=SimpleNamespace())  # type: ignore[arg-type]
        if self.i >= len(self.pieces):
            raise StopAsyncIteration
        self.i += 1
        return self.pieces[self.i - 1]

    async def close(self) -> None:
        self.closed = True


class FakeCompletions:
    def __init__(self, stream: FakeStream | None = None, error: Exception | None = None):
        self.stream = stream
        self.error = error
        self.requests: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> FakeStream:
        self.requests.append(kwargs)
        if self.error:
            raise self.error
        assert self.stream is not None
        return self.stream


def generator(completions: FakeCompletions, timeout: float | None = None) -> OpenAIAnswerGenerator:
    config = load_llm_config()
    if timeout is not None:
        config = config.model_copy(update={"first_token_timeout_seconds": timeout})
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return OpenAIAnswerGenerator("", config, client=client)


CHUNKS = [
    RetrievedChunk(
        chunk_id="c1",
        content="Use create_agent.",
        permalink="",
        source_key="langchain_v1x",
        file_path="agents.mdx",
        heading_path="Agents",
        token_count=5,
        site_url="",
        similarity=0.8,
    )
]


async def collect(gen: OpenAIAnswerGenerator) -> tuple[list[str], Any]:
    stream = gen.generate_stream(
        "q", CHUNKS, display_name="LangChain v1.x", prompt_version="single_v1"
    )
    return [text async for text in stream], stream


async def test_streams_tokens_and_reports_model_finish_and_usage() -> None:
    fake = FakeStream(
        [piece(role="assistant"), piece("LangChain "), piece("v1.x 기준 [1]"), piece(finish="stop"),
         usage_piece(1240, 312)]
    )  # fmt: skip
    completions = FakeCompletions(fake)

    tokens, stream = await collect(generator(completions))

    assert tokens == ["LangChain ", "v1.x 기준 [1]"]
    assert (stream.model, stream.finish_reason) == (MODEL, "stop")
    assert stream.usage == {"prompt": 1240, "completion": 312}
    assert fake.closed


async def test_request_uses_policy_parameters() -> None:
    completions = FakeCompletions(FakeStream([piece("a", "stop")]))

    await collect(generator(completions))

    [request] = completions.requests
    assert request["model"] == "gpt-4o-mini"
    assert (request["temperature"], request["max_tokens"], request["stream"]) == (0, 1024, True)
    assert request["stream_options"] == {"include_usage": True}
    assert request["messages"][0]["role"] == "system"
    assert request["messages"][1] == {"role": "user", "content": "q"}


async def test_first_token_timeout_raises_and_closes_stream() -> None:
    fake = FakeStream([piece("late")], delay=0.2)

    with pytest.raises(LLMCallError, match="첫 토큰"):
        await collect(generator(FakeCompletions(fake), timeout=0.05))
    assert fake.closed


async def test_openai_errors_become_llm_call_error() -> None:
    error = openai.APIConnectionError(request=SimpleNamespace())  # type: ignore[arg-type]
    with pytest.raises(LLMCallError):
        await collect(generator(FakeCompletions(error=error)))

    fake = FakeStream([piece("a"), piece("b")], fail_at=1)
    with pytest.raises(LLMCallError):
        await collect(generator(FakeCompletions(fake)))
    assert fake.closed


async def test_aclose_mid_stream_closes_openai_stream() -> None:
    fake = FakeStream([piece("a"), piece("b"), piece(finish="stop"), usage_piece(1, 2)])
    stream = generator(FakeCompletions(fake)).generate_stream(
        "q", CHUNKS, display_name="x", prompt_version="single_v1"
    )

    assert await stream.__anext__() == "a"
    await stream.aclose()

    assert fake.closed
    assert stream.usage is None  # 중간에 닫으면 사용량 없음


async def test_unknown_prompt_version_fails_before_calling_openai() -> None:
    completions = FakeCompletions(FakeStream([]))

    with pytest.raises(PromptNotFoundError):
        generator(completions).generate_stream("q", CHUNKS, display_name="x", prompt_version="v9")
    assert completions.requests == []


def test_requires_api_key_without_injected_client() -> None:
    with pytest.raises(LLMCallError):
        OpenAIAnswerGenerator("", load_llm_config())

"""단일 모드 OpenAI 스트리밍 생성기 — interfaces.md AnswerGenerator, 정책서 §5.5·§2.1.

- temperature 0 · `max_tokens` 1,024 · 재시도 없음 (`configs/models.yaml` `llm`).
- 요청부터 첫 내용 조각까지 10초를 넘으면 `LLMCallError` (정책서 §2.1 "OpenAI 생성 첫 토큰").
- `aclose()`나 취소로 닫으면 OpenAI 스트림을 닫는다(토큰 과금 최소화, rag-pipeline §3.6).
- sentinel·인용 판정은 하지 않는다. 라우터 조립 단계(R-4-4)가 한다.
"""

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable, Sequence
from typing import Any, TypedDict

import openai

from src.config.rag_config import LlmConfig
from src.domain.retrieval import RetrievedChunk
from src.pipeline.prompts import build_messages


class LLMCallError(Exception):
    """OpenAI 호출 실패 또는 첫 토큰 타임아웃 — 스트림 시작 후에는 error 이벤트 `LLM_ERROR`."""

    code = "LLM_ERROR"


class TokenUsage(TypedDict):
    prompt: int
    completion: int


class OpenAIGenerationStream:
    """토큰 `AsyncIterator[str]`. 끝까지 읽으면 `model`·`finish_reason`·`usage`가 채워진다."""

    def __init__(self, open_stream: Callable[[], Awaitable[Any]], first_token_timeout: float):
        self.model: str | None = None
        self.finish_reason: str | None = None
        self.usage: TokenUsage | None = None
        self._open_stream = open_stream
        self._first_token_timeout = first_token_timeout
        self._stream: Any = None  # OpenAI AsyncStream (close 대상)
        self._chunks: Any = None  # 그 스트림의 단일 이터레이터 (head와 나머지를 이어 읽는다)
        self._tokens = self._run()

    def __aiter__(self) -> "OpenAIGenerationStream":
        return self

    async def __anext__(self) -> str:
        return await self._tokens.__anext__()

    async def aclose(self) -> None:
        await self._tokens.aclose()

    async def _run(self) -> AsyncGenerator[str]:
        try:
            try:
                head = await asyncio.wait_for(self._read_head(), self._first_token_timeout)
            except TimeoutError:
                raise LLMCallError(
                    f"첫 토큰이 {self._first_token_timeout:g}초 안에 오지 않았습니다"
                ) from None
            for text in head:
                yield text
            if self._chunks is not None:
                async for chunk in self._chunks:
                    for text in self._absorb(chunk):
                        yield text
        except openai.OpenAIError as exc:
            raise LLMCallError(f"OpenAI 생성 실패: {type(exc).__name__}: {exc}") from exc
        finally:
            await self._close_stream()

    async def _read_head(self) -> list[str]:
        """스트림을 열고 첫 내용 조각(또는 스트림 끝)까지 읽는다."""
        self._stream = await self._open_stream()
        self._chunks = aiter(self._stream)
        async for chunk in self._chunks:
            texts = self._absorb(chunk)
            if texts:
                return texts
        return []

    def _absorb(self, chunk: Any) -> list[str]:
        if getattr(chunk, "model", None):
            self.model = chunk.model
        usage = getattr(chunk, "usage", None)
        if usage is not None:
            self.usage = TokenUsage(
                prompt=int(usage.prompt_tokens), completion=int(usage.completion_tokens)
            )
        texts: list[str] = []
        for choice in getattr(chunk, "choices", None) or []:
            if choice.finish_reason:
                self.finish_reason = choice.finish_reason
            content = getattr(choice.delta, "content", None)
            if content:
                texts.append(content)
        return texts

    async def _close_stream(self) -> None:
        # 중간에 닫을 때 내부 이터레이터를 먼저 닫는다. 남겨 두면 GC가 나중에 정리하면서
        # "async generator already executing" 경고를 낸다 (#108).
        if self._chunks is not None and hasattr(self._chunks, "aclose"):
            await self._chunks.aclose()
        if self._stream is not None and hasattr(self._stream, "close"):
            await self._stream.close()


class OpenAIAnswerGenerator:
    """단일 모드 생성기. 모델은 `LLM_MODEL` → `models.yaml` 순서로 정한다."""

    def __init__(
        self, api_key: str, config: LlmConfig, *, model_override: str = "", client: Any = None
    ) -> None:
        if client is None and not api_key:
            raise LLMCallError("OPENAI_API_KEY가 설정되지 않아 답변을 생성할 수 없습니다")
        self.config = config
        self.model = config.resolve_model(model_override)
        self.client: Any = client or openai.AsyncOpenAI(
            api_key=api_key, max_retries=config.max_retries
        )

    def generate_stream(
        self,
        query: str,
        chunks: Sequence[RetrievedChunk],
        *,
        display_name: str,
        prompt_version: str,
    ) -> OpenAIGenerationStream:
        """프롬프트가 없으면 즉시 `PromptNotFoundError`. OpenAI 호출은 첫 이터레이션에서 한다."""
        messages = build_messages(
            prompt_version, display_name=display_name, question=query, chunks=chunks
        )
        request = {
            "model": self.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},  # 마지막 조각에 사용량
        }
        return OpenAIGenerationStream(
            lambda: self.client.chat.completions.create(**request),
            self.config.first_token_timeout_seconds,
        )

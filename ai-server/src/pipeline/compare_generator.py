"""비교 모드 구조화 출력 생성기 — interfaces.md `CompareGenerator`, 정책서 §5.6, ADR-010.

- OpenAI Structured Outputs 비스트리밍 1회 호출. temperature 0 · `max_tokens` 1,500
  (`configs/models.yaml` `compare`).
- 파싱 실패(스키마 불일치·`finish_reason=length`·거절·빈 결과)는 `parse_retries`만큼 다시 부르고,
  그래도 실패하면 `CompareParseError` → `error(COMPARE_PARSE_ERROR)`.
- 호출 오류(연결·상태 코드·제한 시간)는 재시도하지 않고 `LLMCallError` → `error(LLM_ERROR)`.
- 인용 후처리·`no_evidence` 고정은 하지 않는다. 파이프라인이 `compare_checks`로 한다.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import openai
import pydantic

from src.config.rag_config import CompareModelConfig
from src.domain.compare import CompareResult
from src.domain.retrieval import RetrievedChunk
from src.pipeline.generator import LLMCallError, TokenUsage
from src.pipeline.prompts import build_compare_messages

logger = logging.getLogger(__name__)


class CompareParseError(Exception):
    """구조화 출력 파싱 실패가 재시도 후에도 남음 — `error` 이벤트 `COMPARE_PARSE_ERROR`."""

    code = "COMPARE_PARSE_ERROR"


@dataclass(frozen=True)
class CompareGeneration:
    result: CompareResult  # 후처리 전 모델 출력
    model: str | None  # 실제 응답 모델명 (INV-13)
    usage: TokenUsage | None  # 재시도 포함 합계
    attempts: int


class _ParseFailure(Exception):
    """한 번의 호출이 파싱 가능한 결과를 내지 못함 (재시도 대상)."""

    def __init__(self, reason: str, usage: Any = None) -> None:
        super().__init__(reason)
        self.usage = usage


def _add(total: TokenUsage | None, usage: Any) -> TokenUsage | None:
    if usage is None:
        return total
    prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion = int(getattr(usage, "completion_tokens", 0) or 0)
    if total is None:
        return TokenUsage(prompt=prompt, completion=completion)
    return TokenUsage(prompt=total["prompt"] + prompt, completion=total["completion"] + completion)


class OpenAICompareGenerator:
    """비교 모드 생성기. 모델은 `LLM_MODEL` → `models.yaml compare` 순서로 정한다."""

    def __init__(
        self,
        api_key: str,
        config: CompareModelConfig,
        *,
        model_override: str = "",
        client: Any = None,
    ) -> None:
        if client is None and not api_key:
            raise LLMCallError("OPENAI_API_KEY가 설정되지 않아 비교 결과를 생성할 수 없습니다")
        self.config = config
        self.model = config.resolve_model(model_override)
        self.client: Any = client or openai.AsyncOpenAI(
            api_key=api_key, max_retries=config.max_retries
        )

    async def generate_compare(
        self,
        query: str,
        chunks_a: Sequence[RetrievedChunk],
        chunks_b: Sequence[RetrievedChunk],
        *,
        display_name_a: str,
        display_name_b: str,
        prompt_version: str,
    ) -> CompareGeneration:
        """프롬프트가 없으면 호출 전에 `PromptNotFoundError`."""
        messages = build_compare_messages(
            prompt_version,
            display_name_a=display_name_a,
            display_name_b=display_name_b,
            question=query,
            chunks_a=chunks_a,
            chunks_b=chunks_b,
        )
        usage: TokenUsage | None = None
        attempts = 0
        last: _ParseFailure | None = None
        while attempts <= self.config.parse_retries:
            attempts += 1
            try:
                result, model, call_usage = await self._call(messages)
            except _ParseFailure as failure:
                usage = _add(usage, failure.usage)
                last = failure
                logger.warning(
                    "compare_parse_failed", extra={"attempt": attempts, "reason": str(failure)}
                )
                continue
            return CompareGeneration(result, model, _add(usage, call_usage), attempts)
        raise CompareParseError(f"비교 결과 파싱 실패 {attempts}회: {last}")

    async def _call(self, messages: list[dict[str, str]]) -> tuple[CompareResult, str | None, Any]:
        try:
            response = await self.client.chat.completions.parse(
                model=self.model,
                messages=messages,
                response_format=CompareResult,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                timeout=self.config.timeout_seconds,
            )
        except (openai.LengthFinishReasonError, openai.ContentFilterFinishReasonError) as exc:
            completion = getattr(exc, "completion", None)
            raise _ParseFailure(type(exc).__name__, getattr(completion, "usage", None)) from exc
        except pydantic.ValidationError as exc:
            raise _ParseFailure(f"스키마 불일치: {exc.error_count()}건") from exc
        except openai.OpenAIError as exc:
            raise LLMCallError(f"OpenAI 비교 생성 실패: {type(exc).__name__}: {exc}") from exc

        choice = response.choices[0] if response.choices else None
        message = getattr(choice, "message", None)
        parsed = getattr(message, "parsed", None)
        if getattr(message, "refusal", None) or not isinstance(parsed, CompareResult):
            raise _ParseFailure("거절 또는 빈 결과", response.usage)
        return parsed, getattr(response, "model", None), response.usage

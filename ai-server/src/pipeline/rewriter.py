"""멀티턴 질의 재작성 — ADR-009, 정책서 §5.2, rag-pipeline.md §3.1.

- 이력이 비면 LLM을 부르지 않고 원래 질문을 쓴다(SKIPPED).
- 최근 `history_turns` 턴만 참조하고 이전 assistant 본문은 앞 `assistant_max_chars`자만 쓴다.
- 제한 시간 초과·빈 출력·출력 상한 초과·호출 오류·질문 언어가 바뀐 출력은 원래 질문으로
  되돌린다(FALLBACK, 정책서 §5.2 "원 질문 언어 유지").
  재작성 실패는 답변 실패가 아니므로 호출자에게 예외를 넘기지 않는다.
- 재작성 질의는 검색에만 쓴다. 생성 프롬프트에는 원래 질문이 들어간다(ADR-009).
- 이력에서 실패·근거 부족 답변을 빼는 일은 이력을 만드는 쪽(backend·게스트 화면)이 한다.
"""

import asyncio
import logging
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

import openai

from src.config.rag_config import RewriteConfig, RewriteModelConfig
from src.domain.chat_stream import HistoryMessage
from src.pipeline.prompts import PROMPTS_DIR, load_template

logger = logging.getLogger(__name__)

_HANGUL = re.compile(r"[가-힣]")


def is_korean(text: str) -> bool:
    """한글이 한 글자라도 있으면 한국어 질문으로 본다. 아니면 영어 질문(정책서 §5.1 허용 언어)."""
    return _HANGUL.search(text) is not None


class RewriteStatus(StrEnum):
    OK = "OK"
    FALLBACK = "FALLBACK"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class RewriteResult:
    """검색에 쓸 질의와 기록값.

    `rewritten`은 재작성 성공일 때만 값이 있다(meta.rewrittenQuery). `elapsed_ms`는 재작성을
    시도했으면 걸린 시간, SKIPPED면 None이다(done.latency.rewriteMs).
    """

    query: str
    rewritten: str | None
    status: RewriteStatus
    elapsed_ms: int | None

    @classmethod
    def skipped(cls, question: str) -> "RewriteResult":
        return cls(question, None, RewriteStatus.SKIPPED, None)


class QueryRewriter(Protocol):
    async def rewrite(
        self, question: str, history: Sequence[HistoryMessage], *, request_id: str
    ) -> RewriteResult: ...


class SkippingRewriter:
    """재작성 없이 원래 질문을 쓴다 — 재작성기를 주입하지 않은 파이프라인(평가·테스트)의 기본값."""

    async def rewrite(
        self, question: str, history: Sequence[HistoryMessage], *, request_id: str
    ) -> RewriteResult:
        return RewriteResult.skipped(question)


def recent_history(history: Sequence[HistoryMessage], rules: RewriteConfig) -> list[dict[str, str]]:
    """최근 N턴, 이전 답변은 앞부분만 (정책서 §5.2 참조 범위)."""
    recent = list(history)[-rules.history_messages :]
    return [
        {
            "role": m.role,
            "content": m.content[: rules.assistant_max_chars]
            if m.role == "assistant"
            else m.content,
        }
        for m in recent
    ]


def normalize(output: str | None) -> str:
    """첫 줄만, 앞뒤 공백·따옴표 제거. 모델이 줄바꿈이나 따옴표를 덧붙여도 질의만 남긴다."""
    if not output:
        return ""
    first = output.strip().splitlines()[0] if output.strip() else ""
    return first.strip().strip("\"'`“”‘’").strip()


class OpenAIQueryRewriter:
    """gpt-4o-mini 비스트리밍 호출 한 번. 재시도 없이 제한 시간 안에 끝나지 않으면 폴백."""

    def __init__(
        self,
        api_key: str,
        model: RewriteModelConfig,
        rules: RewriteConfig,
        *,
        client: Any = None,
        clock: Callable[[], float] = time.perf_counter,
        prompts_dir: Path = PROMPTS_DIR,
    ) -> None:
        self.model = model
        self.rules = rules
        self.clock = clock
        self.template = load_template(rules.prompt_version, prompts_dir)  # 없으면 기동 시 실패
        self.client: Any = client or openai.AsyncOpenAI(
            api_key=api_key, max_retries=model.max_retries
        )

    def prompt(self, question: str, history: Sequence[HistoryMessage]) -> str:
        return self.template.render(
            history=recent_history(history, self.rules),
            question=question,
            max_chars=self.rules.max_output_chars,
            korean=is_korean(question),
        )

    async def rewrite(
        self, question: str, history: Sequence[HistoryMessage], *, request_id: str
    ) -> RewriteResult:
        if not history:
            return RewriteResult.skipped(question)
        started = self.clock()
        reason: str | None = None
        text = ""
        try:
            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model=self.model.model,
                    messages=[{"role": "user", "content": self.prompt(question, history)}],
                    temperature=self.model.temperature,
                    max_tokens=self.model.max_tokens,
                ),
                self.model.timeout_seconds,
            )
            text = normalize(response.choices[0].message.content if response.choices else None)
        except TimeoutError:
            reason = "TIMEOUT"
        except openai.OpenAIError as exc:
            reason = f"LLM_ERROR:{type(exc).__name__}"
        elapsed_ms = max(0, round((self.clock() - started) * 1000))
        if reason is None and not text:
            reason = "EMPTY"
        elif reason is None and len(text) > self.rules.max_output_chars:
            reason = "TOO_LONG"
        elif reason is None and not is_korean(question) and is_korean(text):
            reason = "LANGUAGE"
        if reason is not None:
            logger.warning(
                "rewrite_fallback",
                extra={"request_id": request_id, "reason": reason, "rewrite_ms": elapsed_ms},
            )
            return RewriteResult(question, None, RewriteStatus.FALLBACK, elapsed_ms)
        logger.info(
            "rewrite_done",
            extra={"request_id": request_id, "rewrite_ms": elapsed_ms, "rewrite_len": len(text)},
        )
        return RewriteResult(text, text, RewriteStatus.OK, elapsed_ms)

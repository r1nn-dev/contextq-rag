"""멀티턴 질의 재작성 — 폴백·참조 범위 (ADR-009, 정책서 §5.2), 파이프라인 연결 (api-spec §6.1)."""

import asyncio
from types import SimpleNamespace
from typing import Any

import httpx
import openai
import pytest

from src.config.rag_config import RewriteConfig, RewriteModelConfig, load_rag_config
from src.domain.chat_stream import HistoryMessage
from src.pipeline.rewriter import OpenAIQueryRewriter, RewriteResult, RewriteStatus, normalize
from src.pipeline.single import SingleModePipeline, SingleRequest, StreamProgress
from tests.contract.sse_contract import validate_stream
from tests.unit.test_pipeline_single import INDEX, FakeGenerator, FakeSearcher, FakeStream, chunk

MODEL = RewriteModelConfig(
    model="gpt-4o-mini", temperature=0, max_tokens=200, timeout_seconds=0.2, max_retries=0
)
RULES = RewriteConfig()
HISTORY = [
    HistoryMessage(role="user", content="AgentExecutor는 어떻게 초기화하나요?"),
    HistoryMessage(role="assistant", content="AgentExecutor(agent=..., tools=...)로 만듭니다."),
]


class FakeCompletions:
    def __init__(self, content: str | None = None, *, delay: float = 0.0,
                 error: Exception | None = None) -> None:  # fmt: skip
        self.content = content
        self.delay = delay
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        message = SimpleNamespace(content=self.content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def rewriter(completions: FakeCompletions) -> OpenAIQueryRewriter:
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    ticks = iter([0.0, 0.45, 1.0, 2.0])
    return OpenAIQueryRewriter("", MODEL, RULES, client=client, clock=lambda: next(ticks))


async def test_empty_history_skips_without_calling_the_model() -> None:
    completions = FakeCompletions("unused")

    result = await rewriter(completions).rewrite("질문", [], request_id="r")

    assert result == RewriteResult("질문", None, RewriteStatus.SKIPPED, None)
    assert completions.calls == []


async def test_rewritten_query_is_used_and_reported() -> None:
    completions = FakeCompletions('"AgentExecutor 초기화 후 반환값"\n설명은 생략합니다.')

    result = await rewriter(completions).rewrite("그 메서드의 반환값은?", HISTORY, request_id="r")

    assert result.status is RewriteStatus.OK
    assert result.query == result.rewritten == "AgentExecutor 초기화 후 반환값"
    assert result.elapsed_ms == 450
    call = completions.calls[0]
    assert (call["model"], call["temperature"], call["max_tokens"]) == ("gpt-4o-mini", 0, 200)
    prompt = call["messages"][0]["content"]
    assert call["messages"][0]["role"] == "user"
    assert "사용자: AgentExecutor는 어떻게 초기화하나요?" in prompt
    assert "어시스턴트: AgentExecutor(agent=..., tools=...)로 만듭니다." in prompt
    assert prompt.rstrip().endswith("검색 질의(한국어):")
    assert "그 메서드의 반환값은?" in prompt


def test_prompt_uses_last_three_turns_and_cuts_answers_to_500_chars() -> None:
    history = []
    for i in range(5):
        history.append(HistoryMessage(role="user", content=f"질문{i}"))
        history.append(HistoryMessage(role="assistant", content=f"답{i}" + "가" * 1000))

    prompt = rewriter(FakeCompletions()).prompt("다음 질문", history)

    assert "질문1" not in prompt and "질문2" in prompt and "질문4" in prompt
    answer = next(line for line in prompt.splitlines() if line.startswith("어시스턴트: 답4"))
    assert len(answer.removeprefix("어시스턴트: ")) == 500


@pytest.mark.parametrize(
    ("completions", "label"),
    [
        (FakeCompletions("늦은 답", delay=1.0), "timeout"),
        (FakeCompletions("   "), "empty"),
        (FakeCompletions(None), "none"),
        (FakeCompletions("가" * 201), "too long"),
        (FakeCompletions("한국어로 바뀐 질의"), "language"),
        (
            FakeCompletions(
                error=openai.APIConnectionError(
                    request=httpx.Request("POST", "https://api.openai.com")
                )
            ),
            "llm error",
        ),
    ],
)
async def test_failures_fall_back_to_the_original_question(
    completions: FakeCompletions, label: str
) -> None:
    question = "What does it return?" if label == "language" else "그 메서드의 반환값은?"

    result = await rewriter(completions).rewrite(question, HISTORY, request_id="r")

    assert result.status is RewriteStatus.FALLBACK, label
    assert (result.query, result.rewritten) == (question, None)
    assert result.elapsed_ms is not None


async def test_english_question_keeps_an_english_rewrite() -> None:
    completions = FakeCompletions("What does AgentExecutor return?")

    result = await rewriter(completions).rewrite("What does it return?", HISTORY, request_id="r")

    assert (result.status, result.rewritten) == (
        RewriteStatus.OK,
        "What does AgentExecutor return?",
    )


def test_english_question_asks_for_an_english_query() -> None:
    prompt = rewriter(FakeCompletions()).prompt("What does it return?", HISTORY)

    assert "Write the search query in English only." in prompt
    assert prompt.rstrip().endswith("Search query:")


def test_normalize_keeps_only_the_query_line() -> None:
    assert normalize(" “LCEL 체인 스트리밍” \n") == "LCEL 체인 스트리밍"
    assert normalize("") == ""
    assert normalize(None) == ""


class FixedRewriter:
    def __init__(self, result: RewriteResult) -> None:
        self.result = result
        self.calls: list[tuple[str, tuple[HistoryMessage, ...]]] = []

    async def rewrite(self, question: str, history: Any, *, request_id: str) -> RewriteResult:
        self.calls.append((question, tuple(history)))
        return self.result


async def test_pipeline_searches_with_the_rewrite_and_answers_the_original() -> None:
    searcher = FakeSearcher([chunk(1, 0.82)])
    generator = FakeGenerator(FakeStream(["LangChain v1.x 기준", " 답 [1]"]))
    fixed = FixedRewriter(RewriteResult("AgentExecutor 반환값", "AgentExecutor 반환값",
                                        RewriteStatus.OK, 450))  # fmt: skip
    ticks = iter(float(i) for i in range(1, 100))
    pipeline = SingleModePipeline(
        searcher, generator, load_rag_config().retrieval, rewriter=fixed, clock=lambda: next(ticks)
    )
    req = SingleRequest("req-1", "그 메서드의 반환값은?", INDEX, "single_v2", tuple(HISTORY))

    events = [e async for e in pipeline.run(req, StreamProgress(started=0.0))]
    validate_stream(events, leg="upstream")

    meta, *_, done = events
    assert fixed.calls == [("그 메서드의 반환값은?", tuple(HISTORY))]
    assert searcher.calls[0][0] == "AgentExecutor 반환값"
    assert generator.calls[0]["query"] == "그 메서드의 반환값은?"
    assert meta["rewrittenQuery"] == "AgentExecutor 반환값"
    assert done["latency"]["rewriteMs"] == 450


async def test_pipeline_without_history_keeps_rewrite_fields_null() -> None:
    searcher = FakeSearcher([chunk(1, 0.82)])
    generator = FakeGenerator(FakeStream(["LangChain v1.x 기준", " 답 [1]"]))
    pipeline = SingleModePipeline(searcher, generator, load_rag_config().retrieval)
    req = SingleRequest("req-1", "에이전트는?", INDEX, "single_v2")

    meta, *_, done = [e async for e in pipeline.run(req, StreamProgress(started=0.0))]

    assert searcher.calls[0][0] == "에이전트는?"
    assert meta["rewrittenQuery"] is None
    assert done["latency"]["rewriteMs"] is None

"""비교 모드 생성기·후처리 — 정책서 §5.6, rag-pipeline.md §5.3·§5.4 (가짜 OpenAI 클라이언트)."""

import asyncio
from types import SimpleNamespace
from typing import Any

import openai
import pydantic
import pytest

from src.config.rag_config import load_compare_model_config
from src.domain.compare import CompareChange, CompareResult, CompareSide
from src.pipeline.compare_checks import check_compare
from src.pipeline.compare_generator import CompareParseError, OpenAICompareGenerator
from src.pipeline.generator import LLMCallError
from src.pipeline.prompts import PromptNotFoundError, build_compare_messages
from tests.unit.test_pipeline_single import chunk

MODEL = "gpt-4o-mini-2024-07-18"


def result(
    a: str = "v0.3은 AgentExecutor를 쓴다 [A1].",
    b: str = "v1.x는 create_agent를 쓴다 [B1].",
    changes: list[CompareChange] | None = None,
    cite_a: list[str] | None = None,
    cite_b: list[str] | None = None,
    no_a: bool = False,
    no_b: bool = False,
) -> CompareResult:
    return CompareResult(
        version_a=CompareSide(summary=a, citations=cite_a or ["A1"], no_evidence=no_a),
        version_b=CompareSide(summary=b, citations=cite_b or ["B1"], no_evidence=no_b),
        changes=changes
        if changes is not None
        else [
            CompareChange(
                aspect="생성 함수",
                a="AgentExecutor",
                b="create_agent",
                citations_a=["A1"],
                citations_b=["B1"],
            )
        ],  # fmt: skip
    )


# --- 후처리 (check_compare) -------------------------------------------------------------


def test_valid_result_is_kept_as_is() -> None:
    checked = check_compare(result(), count_a=2, count_b=2)

    assert checked.result == result()
    assert checked.invalid_citations == []
    assert checked.dropped_changes == 0


def test_out_of_range_and_cross_side_citations_are_removed() -> None:
    raw = result(
        a="A측 설명 [A1][A9]. 반대 측 [B1], 묶음 [A1, A7].",
        cite_a=["A1", "A9", "B1", "[A2]", " a1 "],
        cite_b=["B1", "B3", "A1"],
    )

    checked = check_compare(raw, count_a=2, count_b=2)

    side_a = checked.result.version_a
    assert side_a.summary == "A측 설명 [A1]. 반대 측, 묶음 [A1]."
    assert side_a.citations == ["A1", "A2"]  # 괄호·공백·대소문자 정리, 중복 제거
    assert checked.result.version_b.citations == ["B1"]
    assert checked.invalid_citations == ["A1", "A7", "A9", "B1", "B3"]


def test_citation_like_text_inside_code_is_untouched() -> None:
    raw = result(a="예시 `x[A9]`와\n```python\nrows[B2]\n```\n끝 [A3]")

    checked = check_compare(raw, count_a=1, count_b=1)

    assert checked.result.version_a.summary == "예시 `x[A9]`와\n```python\nrows[B2]\n```\n끝 "
    assert checked.invalid_citations == ["A3"]


def test_changes_without_both_side_citations_are_dropped() -> None:
    changes = [
        CompareChange(aspect="ok", a="a [A1]", b="b [B2]", citations_a=["A1"], citations_b=["B2"]),
        CompareChange(aspect="A만", a="a", b="b", citations_a=["A1"], citations_b=[]),
        CompareChange(aspect="없는 B", a="a", b="b", citations_a=["A1"], citations_b=["B5"]),
    ]

    checked = check_compare(result(changes=changes), count_a=1, count_b=2)

    assert [c.aspect for c in checked.result.changes] == ["ok"]
    assert checked.dropped_changes == 2
    assert checked.invalid_citations == ["B5"]


@pytest.mark.parametrize(
    ("kwargs", "raw_flags"),
    [
        ({"no_evidence_a": True, "count_a": 0}, {}),  # τ 미달로 서버가 고정
        ({"count_a": 2}, {"no_a": True}),  # 모델이 근거 부족 선언
    ],
)
def test_no_evidence_side_is_emptied_and_changes_are_skipped(
    kwargs: dict[str, Any], raw_flags: dict[str, bool]
) -> None:
    raw = result(a="근거 없는 요약 [A1]", **raw_flags)

    checked = check_compare(raw, count_b=1, **{"count_a": 0, **kwargs})

    assert checked.result.version_a == CompareSide(summary="", citations=[], no_evidence=True)
    assert checked.result.version_b.no_evidence is False
    assert checked.result.changes == []
    assert checked.invalid_citations == []  # 비우는 측의 번호는 세지 않는다


def test_malformed_labels_are_removed_without_breaking_the_contract() -> None:
    checked = check_compare(result(cite_a=["A1", "C3", "A0", "1"]), count_a=1, count_b=1)

    assert checked.result.version_a.citations == ["A1"]
    assert checked.invalid_citations == []  # 계약 패턴(A/B + 1 이상)이 아닌 값은 기록하지 않는다


# --- 프롬프트 ---------------------------------------------------------------------------


def test_compare_messages_number_each_side_and_mark_missing_side() -> None:
    messages = build_compare_messages(
        "compare_v1",
        display_name_a="LangChain v0.3",
        display_name_b="LangChain v1.x",
        question="에이전트 생성은?",
        chunks_a=[],
        chunks_b=[chunk(1, 0.9), chunk(2, 0.8)],
    )

    system = messages[0]["content"]
    assert "[B1] Doc > S1 (src/1.mdx)" in system
    assert "[B2] Doc > S2 (src/2.mdx)" in system
    assert "[A1]" not in system.split("[버전 B 문서]")[0].split("[버전 A 문서]")[1]
    assert "버전 A는 no_evidence를 true" in system
    assert messages[1] == {"role": "user", "content": "에이전트 생성은?"}


# --- 생성기 -----------------------------------------------------------------------------


def usage(prompt: int, completion: int) -> Any:
    return SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion)


def response(parsed: CompareResult | None, refusal: str | None = None) -> Any:
    message = SimpleNamespace(parsed=parsed, refusal=refusal)
    choices = [SimpleNamespace(message=message)]
    return SimpleNamespace(model=MODEL, usage=usage(1000, 300), choices=choices)


class FakeCompletions:
    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = outcomes
        self.requests: list[dict[str, Any]] = []

    async def parse(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def generator(outcomes: list[Any]) -> tuple[OpenAICompareGenerator, FakeCompletions]:
    completions = FakeCompletions(outcomes)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return OpenAICompareGenerator("", load_compare_model_config(), client=client), completions


def run(gen: OpenAICompareGenerator) -> Any:
    return asyncio.run(
        gen.generate_compare(
            "q", [chunk(1, 0.9)], [chunk(2, 0.9)],
            display_name_a="LangChain v0.3", display_name_b="LangChain v1.x",
            prompt_version="compare_v1",
        )
    )  # fmt: skip


def validation_error() -> pydantic.ValidationError:
    try:
        CompareResult.model_validate_json('{"version_a": {}}')
    except pydantic.ValidationError as exc:
        return exc
    raise AssertionError("unreachable")


def test_generates_with_policy_parameters() -> None:
    gen, completions = generator([response(result())])

    out = run(gen)

    assert out.result == result()
    assert (out.model, out.usage, out.attempts) == (MODEL, {"prompt": 1000, "completion": 300}, 1)
    request = completions.requests[0]
    assert request["response_format"] is CompareResult
    assert (request["temperature"], request["max_tokens"]) == (0, 1500)
    assert request["timeout"] == 25


@pytest.mark.parametrize(
    "failure",
    [
        "validation",
        "refusal",
        "empty",
        "length",
    ],
)
def test_parse_failure_is_retried_once(failure: str) -> None:
    first: Any = {
        "validation": validation_error(),
        "refusal": response(None, refusal="I can't"),
        "empty": response(None),
        "length": openai.LengthFinishReasonError(completion=response(None)),  # type: ignore[arg-type]
    }[failure]
    gen, completions = generator([first, response(result())])

    out = run(gen)

    assert out.attempts == 2
    assert len(completions.requests) == 2
    if failure in ("refusal", "empty", "length"):  # 실패한 호출의 사용량도 합산한다
        assert out.usage == {"prompt": 2000, "completion": 600}


def test_two_parse_failures_raise_compare_parse_error() -> None:
    gen, completions = generator([validation_error(), response(None, refusal="no")])

    with pytest.raises(CompareParseError):
        run(gen)
    assert len(completions.requests) == 2


def test_api_error_is_not_retried() -> None:
    error = openai.APITimeoutError(request=SimpleNamespace())  # type: ignore[arg-type]
    gen, completions = generator([error, response(result())])

    with pytest.raises(LLMCallError):
        run(gen)
    assert len(completions.requests) == 1


def test_unknown_prompt_fails_before_calling() -> None:
    gen, completions = generator([response(result())])

    with pytest.raises(PromptNotFoundError):
        asyncio.run(
            gen.generate_compare(
                "q", [], [], display_name_a="a", display_name_b="b", prompt_version="compare_v9"
            )  # fmt: skip
        )
    assert completions.requests == []


def test_requires_api_key_without_client() -> None:
    with pytest.raises(LLMCallError):
        OpenAICompareGenerator("", load_compare_model_config())

"""sentinel 감지(LLM_ABSTAIN)와 인용 검증(INV-08) — 정책서 §5.4·§5.5·§7."""

import pytest

from src.pipeline.citations import cited_numbers, invalid_citations
from src.pipeline.sentinel import GateState, SentinelGate


def run(tokens: list[str]) -> tuple[str, SentinelGate]:
    gate = SentinelGate()
    out = "".join(gate.feed(t) for t in tokens) + gate.flush()
    return out, gate


@pytest.mark.parametrize(
    "tokens",
    [
        ["[[NO_ANSWER]]"],
        ["[[", "NO_", "ANS", "WER]]"],  # 조각난 sentinel
        ["\n ", "[[NO_ANSWER", "]]", " 근거가 없습니다"],  # 앞 공백, 뒤 문장도 버림
    ],
)
def test_sentinel_at_start_emits_nothing(tokens: list[str]) -> None:
    out, gate = run(tokens)

    assert out == ""
    assert gate.abstained


def test_normal_answer_is_released_as_soon_as_it_cannot_be_sentinel() -> None:
    gate = SentinelGate()

    assert gate.feed("Lang") == "Lang"  # 'L'은 sentinel 접두어가 아님 → 즉시 방출
    assert gate.state is GateState.PASS
    assert gate.feed("Chain") == "Chain"


def test_bracket_start_is_held_until_it_diverges() -> None:
    gate = SentinelGate()

    assert gate.feed("[") == ""
    assert gate.feed("1] 문서") == "[1] 문서"  # sentinel 접두어가 아니게 된 순간 보류분 방출
    assert not gate.abstained


def test_short_answer_held_to_end_is_flushed() -> None:
    out, gate = run(["[[NO"])  # 끝까지 sentinel 접두어였지만 sentinel은 아님

    assert out == "[[NO"
    assert gate.state is GateState.PASS


def test_sentinel_later_in_answer_is_not_abstain() -> None:
    out, gate = run(["답변입니다 [1]. ", "[[NO_ANSWER]]"])

    assert out == "답변입니다 [1]. [[NO_ANSWER]]"
    assert not gate.abstained


def test_buffer_is_capped_at_16_characters() -> None:
    gate = SentinelGate()

    assert gate.feed(" " * 15) == ""
    assert gate.feed(" ") == " " * 16  # 16자에 도달하면 판정 종료 → 방출
    assert gate.state is GateState.PASS


HEADER = "LangChain v1.x 기준"


def run_with_header(tokens: list[str]) -> tuple[str, SentinelGate]:
    gate = SentinelGate(header=HEADER)
    out = "".join(gate.feed(t) for t in tokens) + gate.flush()
    return out, gate


@pytest.mark.parametrize(
    "tokens",
    [
        ["LangChain v1.x 기준 [[NO_ANSWER]]"],  # #108 실측 형태
        ["Lang", "Chain", " v1.x", " 기준", "\n\n", "[[NO_", "ANSWER]]"],  # 조각 + 줄바꿈
        ["[[NO_ANSWER]]"],  # 머리말 없는 sentinel도 그대로 감지
    ],
)
def test_sentinel_after_version_header_emits_nothing(tokens: list[str]) -> None:
    out, gate = run_with_header(tokens)

    assert out == ""
    assert gate.abstained


def test_answer_with_header_is_released_when_body_starts() -> None:
    gate = SentinelGate(header=HEADER)

    assert gate.feed("LangChain v1.x") == ""  # 머리말 접두어 → 보류
    assert gate.feed(" 기준\n\n") == ""  # 머리말 뒤 공백 → 아직 sentinel일 수 있음
    assert gate.feed("에이전트는") == "LangChain v1.x 기준\n\n에이전트는"
    assert gate.state is GateState.PASS


def test_text_that_is_not_header_is_released_immediately() -> None:
    gate = SentinelGate(header=HEADER)

    assert gate.feed("에이") == "에이"  # 머리말·sentinel 어느 쪽의 접두어도 아님
    assert gate.state is GateState.PASS


def test_header_with_other_version_is_not_held() -> None:
    out, gate = run_with_header(["LangChain v0.3 기준 [[NO_ANSWER]]"])

    assert out == "LangChain v0.3 기준 [[NO_ANSWER]]"  # 요청 버전과 다른 머리말은 판정 대상 아님
    assert not gate.abstained


def test_buffer_limit_grows_by_header_length() -> None:
    gate = SentinelGate(header=HEADER)

    assert gate.feed(HEADER + " " * 15) == ""
    assert gate.feed(" ") == HEADER + " " * 16  # 머리말 + 16자에서 판정 종료
    assert gate.state is GateState.PASS


def test_cited_numbers_parses_single_and_grouped_citations() -> None:
    answer = "LangChain v1.x 기준 [1]. 도구는 [2][3] 또는 [3, 4]로 정의한다 [10]."

    assert cited_numbers(answer) == [1, 2, 3, 4, 10]


def test_invalid_citations_are_out_of_source_range() -> None:
    answer = "설명 [1] [3] [0] [7, 2]"

    assert invalid_citations(answer, source_count=3) == [0, 7]
    assert invalid_citations("인용 없음", source_count=0) == []


def test_brackets_in_code_are_not_citations() -> None:
    answer = (
        "`items[0]`처럼 접근한다 [1].\n"
        "```python\nresult = chain.invoke(x)[9]\n```\n"
        "그리고 [2].\n"
        "~~~\nfoo[5]\n~~~\n"
        "```python\ncut_off[8]"  # max_tokens로 잘린 펜스
    )

    assert cited_numbers(answer) == [1, 2]

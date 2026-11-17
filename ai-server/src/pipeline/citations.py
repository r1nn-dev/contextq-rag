"""인용 번호 검증 — 정책서 §5.5 "인용 검증"·§7 인용 규칙, INV-08.

- 본문의 `[n]`·`[n, m]`을 파싱해 meta.sources rank 범위(1..source_count) 밖 번호를 찾는다.
- 코드 펜스·인라인 코드 안의 대괄호(`arr[0]` 등)는 인용으로 보지 않는다.
- `max_tokens`로 잘려 닫히지 않은 펜스는 끝까지 코드로 본다.
"""

import re

_CLOSED_FENCE = re.compile(r"(```|~~~).*?\1", re.DOTALL)
_OPEN_FENCE = re.compile(r"(```|~~~).*\Z", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_CITATION = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


def _prose(answer: str) -> str:
    text = _CLOSED_FENCE.sub(" ", answer)
    text = _OPEN_FENCE.sub(" ", text)
    return _INLINE_CODE.sub(" ", text)


def cited_numbers(answer: str) -> list[int]:
    """본문에 나온 인용 번호 (오름차순, 중복 없음)."""
    numbers = {
        int(part) for match in _CITATION.finditer(_prose(answer)) for part in match[1].split(",")
    }
    return sorted(numbers)


def invalid_citations(answer: str, source_count: int) -> list[int]:
    """meta.sources 범위 밖 인용 번호 → done.invalidCitations (INV-08)."""
    return [n for n in cited_numbers(answer) if not 1 <= n <= source_count]

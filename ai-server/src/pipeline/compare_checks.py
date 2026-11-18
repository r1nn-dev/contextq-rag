"""비교 결과 후처리 검증 — 정책서 §5.6 "후처리 검증", rag-pipeline.md §5.3, INV-08.

- 인용 배열과 본문 `[A1]` 표시에서 그 측의 출처 범위 밖 번호·반대 측 번호를 지운다.
- 코드 펜스·인라인 코드 안의 대괄호는 인용으로 보지 않는다(단일 모드 `citations.py`와 같은 기준).
- `no_evidence` 측은 요약·인용을 비우고, 한쪽이라도 근거가 없으면 변경점을 만들지 않는다.
- 변경점은 A·B 인용이 모두 남아 있을 때만 유지한다("양쪽 근거 인용 필수").
- 지운 번호는 `done.invalidCitations`로 보낸다. 비우는 측(no_evidence)의 번호는 세지 않는다.
  계약(`citation` 패턴 `^[AB][1-9][0-9]*$`)에 맞지 않는 값은 지우기만 하고 기록하지 않는다.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from src.domain.compare import CompareChange, CompareResult, CompareSide

_LABEL = re.compile(r"^([AB])([1-9][0-9]*)$")
_INLINE = re.compile(r"\[\s*([AB][0-9]+(?:\s*,\s*[AB][0-9]+)*)\s*\]")
_CODE = re.compile(r"(```|~~~).*?(?:\1|\Z)|`[^`\n]*`", re.DOTALL)


@dataclass(frozen=True)
class CompareCheck:
    result: CompareResult
    invalid_citations: list[str]  # 지운 번호 (A 먼저, 번호 순)
    dropped_changes: int  # 양쪽 인용이 없어 버린 변경점 수


@dataclass
class _Side:
    prefix: str  # "A" | "B"
    count: int  # 그 측 출처 수 (meta.sources)
    invalid: set[str] = field(default_factory=set)

    def reject(self, label: str) -> None:
        if _LABEL.match(label):
            self.invalid.add(label)

    def valid(self, label: str) -> bool:
        match = _LABEL.match(label)
        if match is None:
            return False
        return match[1] == self.prefix and 1 <= int(match[2]) <= self.count

    def labels(self, raw: Iterable[str]) -> list[str]:
        """인용 배열 정리 — 괄호·공백 제거, 순서 유지·중복 제거, 범위 밖은 기록 후 제외."""
        kept: list[str] = []
        for item in raw:
            label = item.strip().strip("[]").strip().upper()
            if not self.valid(label):
                self.reject(label)
            elif label not in kept:
                kept.append(label)
        return kept

    def text(self, value: str) -> str:
        """본문의 `[A1]`·`[A1, A2]` 표시에서 잘못된 번호를 지운다. 코드 안은 그대로 둔다."""
        out: list[str] = []
        last = 0
        for code in _CODE.finditer(value):
            out.append(self._prose(value[last : code.start()]))
            out.append(code.group(0))
            last = code.end()
        out.append(self._prose(value[last:]))
        return "".join(out)

    def _prose(self, value: str) -> str:
        def keep(match: re.Match[str]) -> str:
            labels = [part.strip() for part in match[1].split(",")]
            valid = [label for label in labels if self.valid(label)]
            for label in labels:
                if not self.valid(label):
                    self.reject(label)
            return f"[{', '.join(valid)}]" if valid else ""

        cleaned = _INLINE.sub(keep, value)
        return re.sub(r"[ \t]+([.,!?)])", r"\1", cleaned) if cleaned != value else value


def _sort_key(label: str) -> tuple[str, int]:
    match = _LABEL.match(label)
    return (match[1], int(match[2])) if match else ("~", 0)


def check_compare(
    result: CompareResult,
    *,
    count_a: int,
    count_b: int,
    no_evidence_a: bool = False,
    no_evidence_b: bool = False,
) -> CompareCheck:
    """`count_*`는 그 측 컨텍스트(출처) 수, `no_evidence_*`는 τ 미달로 고정할 측."""
    side_a, side_b = _Side("A", count_a), _Side("B", count_b)
    empty_a = no_evidence_a or count_a == 0 or result.version_a.no_evidence
    empty_b = no_evidence_b or count_b == 0 or result.version_b.no_evidence

    def side(raw: CompareSide, rules: _Side, empty: bool) -> CompareSide:
        if empty:
            return CompareSide(summary="", citations=[], no_evidence=True)
        return CompareSide(
            summary=rules.text(raw.summary),
            citations=rules.labels(raw.citations),
            no_evidence=False,
        )

    version_a = side(result.version_a, side_a, empty_a)
    version_b = side(result.version_b, side_b, empty_b)

    changes: list[CompareChange] = []
    dropped = 0
    if not (empty_a or empty_b):
        for change in result.changes:
            cited_a = side_a.labels(change.citations_a)
            cited_b = side_b.labels(change.citations_b)
            if not cited_a or not cited_b:
                dropped += 1
                continue
            changes.append(
                CompareChange(
                    aspect=change.aspect,
                    a=side_a.text(change.a),
                    b=side_b.text(change.b),
                    citations_a=cited_a,
                    citations_b=cited_b,
                )
            )
    else:
        dropped = len(result.changes)

    invalid = sorted(side_a.invalid | side_b.invalid, key=_sort_key)
    return CompareCheck(
        CompareResult(version_a=version_a, version_b=version_b, changes=changes),
        invalid,
        dropped,
    )

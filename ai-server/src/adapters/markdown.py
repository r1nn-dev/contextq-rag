"""포맷 공통 전처리 — 원문 라인 번호를 단 줄 단위로 처리한다 (doc-source.md §4.1·§5).

모든 함수는 `Line` 목록을 받아 새 목록을 돌려준다. 줄을 지워도 남은 줄의 원문 번호는
그대로라서, 전처리 후에도 라인 앵커 permalink(ADR-007)의 근거가 유지된다.
코드 펜스 안의 줄은 어떤 규칙도 적용하지 않는다(정책서 §4.3 "코드 펜스 내부 diff 0").
"""

import re
from dataclasses import dataclass

import yaml

from src.domain.documents import Section

MIN_SECTION_CHARS = 50  # 정책서 §4.3 빈 섹션 기준
MAX_HEADING_LEVEL = 3  # H4 이하는 heading_path에 넣지 않는다 (doc-source.md §5)


@dataclass(frozen=True)
class Line:
    no: int  # 원문 라인 번호 (1부터)
    text: str


def to_lines(raw: str) -> list[Line]:
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    return [Line(i, t) for i, t in enumerate(text.split("\n"), start=1)]


# --- frontmatter -------------------------------------------------------------


def strip_frontmatter(lines: list[Line]) -> tuple[str | None, list[Line]]:
    """파일 첫 줄의 `---` 블록을 지우고 `title`을 돌려준다."""
    if not lines or lines[0].text.strip() != "---":
        return None, lines
    for idx in range(1, len(lines)):
        if lines[idx].text.strip() == "---":
            body = "\n".join(line.text for line in lines[1:idx])
            try:
                meta = yaml.safe_load(body) or {}
            except yaml.YAMLError:
                meta = {}
            title = meta.get("title") if isinstance(meta, dict) else None
            return (str(title).strip() if title else None), lines[idx + 1 :]
    return None, lines


# --- 코드 펜스 ----------------------------------------------------------------

_FENCE_OPEN = re.compile(r"^\s*(`{3,}|~{3,})")


def fence_mask(lines: list[Line]) -> list[bool]:
    """펜스 줄과 펜스 내부 줄이면 True. 들여쓴 펜스(JSX 안)도 인식한다."""
    mask: list[bool] = []
    marker: str | None = None
    for line in lines:
        if marker is None:
            match = _FENCE_OPEN.match(line.text)
            if match:
                marker = match.group(1)
                mask.append(True)
            else:
                mask.append(False)
        else:
            mask.append(True)
            stripped = line.text.strip()
            if stripped.startswith(marker[0] * len(marker)) and set(stripped) == {marker[0]}:
                marker = None
    return mask


def has_code_fence(text: str) -> bool:
    return any(_FENCE_OPEN.match(line) for line in text.split("\n"))


# --- MDX import / export ------------------------------------------------------

_IMPORT = re.compile(r"^import\s+(?:.+\s+from\s+)?['\"]")
_EXPORT = re.compile(r"^export\s+(?:const|let|var|default|function|async)\b")


def _bracket_balance(text: str) -> int:
    return sum(text.count(c) for c in "([{") - sum(text.count(c) for c in ")]}")


def remove_mdx_statements(lines: list[Line]) -> list[Line]:
    """펜스 밖 줄 시작의 MDX import·export 문을 지운다 (여러 줄 export 포함)."""
    mask = fence_mask(lines)
    out: list[Line] = []
    depth = 0
    for line, in_fence in zip(lines, mask, strict=True):
        if depth > 0:
            depth += _bracket_balance(line.text)
            continue
        if not in_fence and (_IMPORT.match(line.text) or _EXPORT.match(line.text)):
            depth = max(_bracket_balance(line.text), 0)
            continue
        out.append(line)
    return out


# --- JSX · HTML 태그 ----------------------------------------------------------

_HTML_TAGS = (
    "a|b|br|center|details|div|em|figcaption|figure|hr|i|iframe|img|li|ol|p|picture|source|"
    "span|strong|sub|summary|sup|table|tbody|td|th|thead|tr|u|ul|video"
)
_TAG_NAME = rf"(?:[A-Z][\w.]*|(?:{_HTML_TAGS})\b)"
_TAG = re.compile(rf"<(/?)({_TAG_NAME})([^<>]*?)(/?)>")
_TAG_START = re.compile(rf"<(/?)({_TAG_NAME})([^<>]*)$")
_TITLE_ATTR = re.compile(r"\btitle=(?:\"([^\"]*)\"|'([^']*)'|\{[\"']([^\"']*)[\"']\})")
_JSX_COMMENT = re.compile(r"\{/\*.*?\*/\}")


def _title_of(attrs: str) -> str:
    match = _TITLE_ATTR.search(attrs)
    if not match:
        return ""
    return next(g for g in match.groups() if g is not None).strip()


def _replace_tags(segment: str) -> str:
    def repl(m: re.Match[str]) -> str:
        closing, _name, attrs, _self = m.groups()
        return "" if closing else _title_of(attrs)

    return _TAG.sub(repl, segment)


def strip_jsx(lines: list[Line]) -> list[Line]:
    """펜스 밖 JSX 주석과 JSX·HTML 태그를 지우고 텍스트 자식과 title 속성을 남긴다.

    인라인 코드(`…`) 안은 건드리지 않는다. 태그 때문에 비게 된 줄은 지운다.
    """
    mask = fence_mask(lines)
    out: list[Line] = []
    in_comment = False
    open_tag_attrs: str | None = None  # 여러 줄에 걸친 여는 태그의 속성 누적

    for line, in_fence in zip(lines, mask, strict=True):
        if in_fence:
            out.append(line)
            continue
        text = line.text

        if in_comment:
            end = text.find("*/}")
            if end < 0:
                continue
            text = text[end + 3 :]
            in_comment = False

        if open_tag_attrs is not None:
            end = text.find(">")
            if end < 0:
                open_tag_attrs += " " + text
                continue
            title = _title_of(open_tag_attrs + " " + text[:end])
            text = title + text[end + 1 :]
            open_tag_attrs = None

        text = _JSX_COMMENT.sub("", text)
        start = text.find("{/*")
        if start >= 0 and "*/}" not in text[start:]:
            text = text[:start]
            in_comment = True

        parts = text.split("`")
        for i in range(0, len(parts), 2):  # 짝수 인덱스 = 인라인 코드 밖
            parts[i] = _replace_tags(parts[i])
        if len(parts) % 2 == 1:
            dangling = _TAG_START.search(parts[-1])
            if dangling:
                parts[-1] = parts[-1][: dangling.start()]
                open_tag_attrs = dangling.group(3)
        new_text = "`".join(parts)

        if new_text.strip() or not line.text.strip():
            out.append(Line(line.no, new_text.rstrip()))
    return out


def collapse_blank_lines(lines: list[Line]) -> list[Line]:
    """펜스 밖의 연속 빈 줄을 1줄로 줄인다."""
    mask = fence_mask(lines)
    out: list[Line] = []
    previous_blank = False
    for line, in_fence in zip(lines, mask, strict=True):
        blank = not in_fence and not line.text.strip()
        if blank and previous_blank:
            continue
        out.append(line)
        previous_blank = blank
    return out


# --- 섹션 분리 ----------------------------------------------------------------

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_ANCHOR = re.compile(r"\s*\{#[^}]*\}\s*$")


def clean_heading(text: str) -> str:
    text = _ANCHOR.sub("", text)
    for token in ("**", "__", "`"):
        text = text.replace(token, "")
    return text.strip()


@dataclass
class _Draft:
    path: str
    lines: list[Line]

    def body_chars(self) -> int:
        body = self.lines[1:] if self.lines and _HEADING.match(self.lines[0].text) else self.lines
        return sum(len("".join(line.text.split())) for line in body)


def _trim(lines: list[Line]) -> list[Line]:
    start, end = 0, len(lines)
    while start < end and not lines[start].text.strip():
        start += 1
    while end > start and not lines[end - 1].text.strip():
        end -= 1
    return lines[start:end]


def build_sections(
    lines: list[Line], title: str, *, min_chars: int = MIN_SECTION_CHARS
) -> list[Section]:
    """H1~H3로 섹션을 나누고, 본문 min_chars 미만 섹션은 바로 앞 섹션에 병합한다."""
    mask = fence_mask(lines)
    levels: dict[int, str] = {1: title}
    drafts: list[_Draft] = [_Draft(title, [])]

    for line, in_fence in zip(lines, mask, strict=True):
        match = None if in_fence else _HEADING.match(line.text)
        if match and len(match.group(1)) <= MAX_HEADING_LEVEL:
            level = len(match.group(1))
            levels[level] = clean_heading(match.group(2)) or levels.get(level, title)
            for deeper in range(level + 1, MAX_HEADING_LEVEL + 1):
                levels.pop(deeper, None)
            path = " > ".join(levels[k] for k in sorted(levels))
            drafts.append(_Draft(path, [line]))
        else:
            drafts[-1].lines.append(line)

    for draft in drafts:
        draft.lines = _trim(draft.lines)
    drafts = [d for d in drafts if d.lines]

    merged: list[_Draft] = []
    carry: _Draft | None = None
    for draft in drafts:
        if carry is not None:
            draft = _Draft(draft.path, carry.lines + draft.lines)
            carry = None
        if draft.body_chars() >= min_chars:
            merged.append(draft)
        elif merged:
            merged[-1].lines.extend(draft.lines)
        else:
            carry = draft  # 문서의 첫 섹션이면 다음 섹션과 합친다
    # 문서 전체가 min_chars 미만이면 섹션을 만들지 않는다 (50자 미만 청크 0건)

    return [
        Section(
            heading_path=d.path,
            text="\n".join(line.text for line in d.lines),
            line_numbers=tuple(line.no for line in d.lines),
        )
        for d in merged
    ]

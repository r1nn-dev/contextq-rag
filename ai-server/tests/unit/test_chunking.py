"""청킹 전략 — 섹션 경계·라인 범위·코드 펜스 (interfaces.md §4·§6.4, test-plan.md 8.1-1)."""

import pytest

from src.config.ingest_config import load_chunking_config
from src.domain.documents import NormalizedDocument, Section
from src.ingest.chunking import (
    ChunkingError,
    line_range,
    make_chunker,
    splits_code_fence,
)

CONFIG = load_chunking_config()


def _section(path: str, lines: list[str], first_line: int) -> Section:
    return Section(path, "\n".join(lines), tuple(range(first_line, first_line + len(lines))))


def _doc(*sections: Section) -> NormalizedDocument:
    return NormalizedDocument("docs/a.mdx", "A", "mdx", "https://x", sections)


def test_line_range_maps_chars_to_original_lines() -> None:
    section = _section("A", ["aa", "bb", "cc"], 120)
    assert line_range(section, 0, 2) == (120, 120)
    assert line_range(section, 3, 5) == (121, 122)


@pytest.mark.parametrize("fence", ["```python", "    ```", "~~~"])
def test_splits_code_fence(fence: str) -> None:
    assert splits_code_fence(f"text\n{fence}\ncode")
    assert not splits_code_fence(f"{fence}\ncode\n{fence}")


@pytest.mark.parametrize("strategy", ["A", "B"])
def test_small_section_becomes_single_chunk(strategy: str) -> None:
    section = _section("A > B", ["## B", "", "short body"], 10)
    chunks = make_chunker(strategy, CONFIG.params(strategy)).chunk(_doc(section))  # type: ignore[arg-type]
    assert chunks == [
        {"content": "## B\n\nshort body", "heading_path": "A > B", "line_start": 10, "line_end": 12}
    ]


@pytest.mark.parametrize("strategy", ["A", "B"])
def test_chunks_never_cross_sections_and_keep_line_bounds(strategy: str) -> None:
    paragraph = "word " * 60  # 300자
    first = _section("T > One", [f"p{i} {paragraph}" for i in range(8)], 120)
    second = _section("T > Two", ["## Two", "tail body text"], 300)
    first = Section(first.heading_path, first.text.replace("\n", "\n\n"), _double(first))
    chunks = make_chunker(strategy, CONFIG.params(strategy)).chunk(_doc(first, second))  # type: ignore[arg-type]

    one = [c for c in chunks if c["heading_path"] == "T > One"]
    assert len(one) > 1
    for chunk in one:
        assert 120 <= chunk["line_start"] <= chunk["line_end"] <= first.line_end
        assert len(chunk["content"]) <= 1000
    assert [c["heading_path"] for c in chunks][-1] == "T > Two"
    assert chunks[-1]["line_start"] == 300


def _double(section: Section) -> tuple[int, ...]:
    # "\n" → "\n\n"로 바꾼 텍스트의 줄 번호: 빈 줄은 앞줄 번호를 공유한다
    numbers: list[int] = []
    for i, no in enumerate(section.line_numbers):
        numbers.append(no)
        if i < len(section.line_numbers) - 1:
            numbers.append(no)
    return tuple(numbers)


def test_document_without_sections_raises() -> None:
    with pytest.raises(ChunkingError):
        make_chunker("B", CONFIG.params("B")).chunk(_doc())

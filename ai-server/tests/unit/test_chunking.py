"""청킹 전략 — 섹션 경계·라인 범위·코드 펜스 (interfaces.md §4·§6.4, test-plan.md 8.1-1)."""

import pytest

from src.config.ingest_config import load_chunking_config
from src.domain.documents import NormalizedDocument, Section
from src.ingest.chunking import (
    ChunkingError,
    line_range,
    make_chunker,
    merge_small,
    splits_code_fence,
    visible_chars,
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


@pytest.mark.parametrize(
    ("opening", "closing"), [("```python", "```"), ("    ```", "    ```"), ("~~~", "~~~")]
)
def test_splits_code_fence(opening: str, closing: str) -> None:
    assert splits_code_fence(f"text\n{opening}\ncode")
    assert not splits_code_fence(f"{opening}\ncode\n{closing}")


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
        assert len(chunk["content"]) <= 1100  # 50자 미만 꼬리 병합분만큼 상한을 넘을 수 있다
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


def test_strategy_c_groups_h3_into_h2() -> None:
    sections = (
        _section("T", ["# T", "intro"], 1),
        _section("T > Tools", ["## Tools", "tools body"], 3),
        _section("T > Tools > Define", ["### Define", "define body"], 5),
        _section("T > Models", ["## Models", "models body"], 7),
    )
    chunks = make_chunker("C", CONFIG.params("C")).chunk(_doc(*sections))
    assert [(c["heading_path"], c["line_start"], c["line_end"]) for c in chunks] == [
        ("T", 1, 2),
        ("T > Tools", 3, 6),
        ("T > Models", 7, 8),
    ]
    assert "### Define" in chunks[1]["content"]


def test_strategy_c_never_splits_code_fences() -> None:
    code = ["```python", *[f"x{i} = {i}  # " + "c" * 40 for i in range(40)], "", "y = 1", "```"]
    prose = ["para " * 50, "", "para " * 50, ""]
    lines = ["## Big", "", *prose, *code, "", "after the fence " * 5]
    section = _section("T > Big", lines, 10)
    chunks = make_chunker("C", CONFIG.params("C")).chunk(_doc(section))

    assert not any(splits_code_fence(c["content"]) for c in chunks)
    fenced = [c for c in chunks if "```python" in c["content"]]
    assert len(fenced) == 1 and len(fenced[0]["content"]) > 1000  # 상한보다 큰 펜스도 한 청크
    assert [c["line_start"] for c in chunks] == sorted(c["line_start"] for c in chunks)
    assert chunks[0]["line_start"] == 10 and chunks[-1]["line_end"] == 10 + len(lines) - 1


def test_backticks_inside_code_string_are_not_a_split() -> None:
    content = '```python\ntemplate = """```python\n{x}\n```"""\nprint(template)\n```'
    assert not splits_code_fence(content)
    assert splits_code_fence("```python\nx = 1")
    assert splits_code_fence("x = 1\n```\nafter")  # 펜스 중간에서 시작한 청크


def test_merge_small_into_previous_or_next() -> None:
    sizes = {(0, 10): 80, (10, 12): 2, (12, 40): 60, (0, 12): 82}
    assert merge_small([(0, 10), (10, 12), (12, 40)], lambda s: sizes.get(s, 100)) == [
        (0, 12),
        (12, 40),
    ]
    first_small = {(0, 2): 2, (0, 30): 70, (30, 60): 60}
    assert merge_small([(0, 2), (2, 30), (30, 60)], lambda s: first_small.get(s, 100)) == [
        (0, 30),
        (30, 60),
    ]


@pytest.mark.parametrize("strategy", ["A", "B", "C"])
def test_no_chunk_below_minimum(strategy: str) -> None:
    body = ("sentence " * 12 + "\n\n") * 12 + "tail"
    section = _section("T > S", body.split("\n"), 1)
    chunks = make_chunker(strategy, CONFIG.params(strategy)).chunk(_doc(section))  # type: ignore[arg-type]
    assert all(visible_chars(c["content"]) >= 50 for c in chunks)
    assert "tail" in chunks[-1]["content"]

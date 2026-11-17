"""포맷 공통 전처리 — 라인 번호 유지, 코드 펜스 보호, 섹션 분리·병합 (doc-source.md §4.1·§5)."""

from src.adapters.markdown import (
    Line,
    build_sections,
    clean_heading,
    collapse_blank_lines,
    fence_mask,
    remove_mdx_statements,
    strip_frontmatter,
    strip_jsx,
    to_lines,
)

BODY = "This paragraph is long enough to stand alone as its own section body."


def _texts(lines: list[Line]) -> list[str]:
    return [line.text for line in lines]


def test_to_lines_numbers_from_one_and_normalizes_crlf() -> None:
    assert to_lines("a\r\nb") == [Line(1, "a"), Line(2, "b")]


def test_strip_frontmatter_returns_title_and_keeps_line_numbers() -> None:
    title, rest = strip_frontmatter(to_lines('---\ntitle: "Agents"\nboost: 2\n---\nbody'))
    assert title == "Agents"
    assert rest == [Line(5, "body")]


def test_strip_frontmatter_without_block() -> None:
    lines = to_lines("# T\nbody")
    assert strip_frontmatter(lines) == (None, lines)


def test_fence_mask_handles_indented_and_nested_markers() -> None:
    lines = to_lines("a\n    ```python\n    x = 1\n    ```\nb\n````md\n```\n````\nc")
    assert fence_mask(lines) == [False, True, True, True, False, True, True, True, False]


def test_remove_mdx_statements_skips_fenced_code() -> None:
    lines = to_lines(
        "import A from '/snippets/a.mdx';\n"
        "export const meta = {\n  a: 1,\n};\n"
        "text\n"
        "```bash\nexport OPENAI_API_KEY=...\nimport x from 'y'\n```"
    )
    assert _texts(remove_mdx_statements(lines)) == [
        "text",
        "```bash",
        "export OPENAI_API_KEY=...",
        "import x from 'y'",
        "```",
    ]


def test_strip_jsx_keeps_text_children_and_titles() -> None:
    lines = to_lines(
        "<Note>\n**Agent = Model + Harness**\n</Note>\n"
        '<Tab title="Python">\n'
        "Use `<Component />` in code and <br/> breaks.\n"
        "{/* hidden */}"
    )
    assert _texts(strip_jsx(lines)) == [
        "**Agent = Model + Harness**",
        "Python",
        "Use `<Component />` in code and  breaks.",
    ]


def test_strip_jsx_multiline_tag_and_comment() -> None:
    lines = to_lines(
        "<img\n"
        '    src="/a.svg"\n'
        '    style={{height: "300px"}}\n'
        "/>\n"
        "{/* start\nhidden\nend */}\n"
        "kept"
    )
    assert strip_jsx(lines) == [Line(8, "kept")]


def test_strip_jsx_leaves_fenced_code_untouched() -> None:
    lines = to_lines('```tsx\n<Tabs title="x">\n```')
    assert strip_jsx(lines) == lines


def test_collapse_blank_lines_outside_fences_only() -> None:
    lines = to_lines("a\n\n\n\nb\n```\n\n\n```")
    assert _texts(collapse_blank_lines(lines)) == ["a", "", "b", "```", "", "", "```"]


def test_clean_heading() -> None:
    assert clean_heading("Using `create_agent` **now** {#custom-id}") == "Using create_agent now"


def test_build_sections_paths_and_line_numbers() -> None:
    lines = to_lines(f"intro {BODY}\n## Tools\n{BODY}\n### Define\n{BODY}\n#### Deep\n{BODY}")
    sections = build_sections(lines, "Agents")

    assert [s.heading_path for s in sections] == [
        "Agents",
        "Agents > Tools",
        "Agents > Tools > Define",
    ]
    assert sections[1].text == f"## Tools\n{BODY}"
    assert sections[1].line_numbers == (2, 3)
    # H4는 섹션을 나누지 않는다
    assert sections[2].line_numbers == (4, 5, 6, 7)


def test_build_sections_h1_replaces_title() -> None:
    sections = build_sections(to_lines(f"# Real Title\n{BODY}\n## Sub\n{BODY}"), "stem")
    assert [s.heading_path for s in sections] == ["Real Title", "Real Title > Sub"]


def test_small_section_merges_into_previous() -> None:
    lines = to_lines(f"## Core\nshort\n### Model\n{BODY}\n### Tiny\ntoo short")
    sections = build_sections(lines, "Agents")

    # "Core"(본문 5자)는 첫 섹션이라 다음 섹션과 합쳐지고, "Tiny"는 바로 앞 섹션에 병합된다
    assert len(sections) == 1
    assert sections[0].heading_path == "Agents > Core > Model"
    assert sections[0].line_numbers == (1, 2, 3, 4, 5, 6)


def test_headings_inside_fences_do_not_split() -> None:
    lines = to_lines(f"## Real\n{BODY}\n```md\n## not a heading\n```")
    sections = build_sections(lines, "T")
    assert [s.heading_path for s in sections] == ["T > Real"]


def test_tiny_document_produces_no_sections() -> None:
    assert build_sections(to_lines("# T\nshort"), "T") == []

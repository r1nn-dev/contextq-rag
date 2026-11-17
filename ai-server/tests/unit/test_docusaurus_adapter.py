"""v0.3 Docusaurus Adapter — 골든 파일 테스트 (doc-source.md §4.3, 정책서 §4.3).

골든 파일을 다시 만들려면: `UPDATE_GOLDEN=1 uv run pytest tests/unit/test_docusaurus_adapter.py`
(다시 만든 뒤에는 diff를 직접 검토한다)
"""

import json
import os
from dataclasses import asdict
from pathlib import Path

import pytest

from src.adapters.base import AdapterContext, create_adapter
from src.adapters.docusaurus import is_included, site_url, strip_admonitions
from src.adapters.markdown import Line, to_lines

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "docusaurus"
GOLDEN = FIXTURES / "expected.json"


def _run() -> tuple[list[dict[str, object]], dict[str, object]]:
    adapter = create_adapter("DocusaurusAdapter", AdapterContext(doc_path="docs/docs/"))
    documents = [asdict(d) for d in adapter.iter_documents(FIXTURES)]
    return documents, asdict(adapter.report)


def test_golden_output() -> None:
    documents, report = _run()
    actual = json.loads(json.dumps({"documents": documents, "report": report}))
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN.write_text(json.dumps(actual, ensure_ascii=False, indent=2) + "\n", "utf-8")
    assert actual == json.loads(GOLDEN.read_text("utf-8"))


def test_notebook_outputs_and_markers_never_reach_text() -> None:
    documents, report = _run()
    texts = "\n".join(s["text"] for d in documents for s in d["sections"])  # type: ignore[union-attr]
    assert "OUTPUT CELL TEXT" not in texts
    assert "ChatModelTabs" not in texts
    assert report["files_by_type"] == {"mdx": 2, "ipynb": 1}


def test_strip_admonitions_keeps_titles_and_fenced_markers() -> None:
    lines = to_lines(
        ":::info Prerequisites\nbody\n:::\n::: note\nn\n:::\n:::tip[Tip title]\n```\n:::\n```"
    )
    assert strip_admonitions(lines) == [
        Line(1, "Prerequisites"),
        Line(2, "body"),
        Line(5, "n"),
        Line(7, "Tip title"),
        Line(8, "```"),
        Line(9, ":::"),
        Line(10, "```"),
    ]


@pytest.mark.parametrize(
    ("rel", "included"),
    [
        ("concepts/lcel.mdx", True),
        ("how_to/tool_calling.ipynb", True),
        ("versions/v0_3/index.mdx", True),
        ("introduction.mdx", True),
        ("integrations/chat/openai.ipynb", False),
        ("contributing/index.md", False),
        ("people.mdx", False),
        ("_templates/integration.mdx", False),
    ],
)
def test_include_exclude_paths(rel: str, included: bool) -> None:
    assert is_included(rel) is included


@pytest.mark.parametrize(
    ("rel", "url"),
    [
        (
            "how_to/tool_calling.ipynb",
            "https://python.langchain.com/v0.3/docs/how_to/tool_calling/",
        ),
        ("how_to/index.mdx", "https://python.langchain.com/v0.3/docs/how_to/"),
        ("introduction.mdx", "https://python.langchain.com/v0.3/docs/introduction/"),
    ],
)
def test_site_url(rel: str, url: str) -> None:
    assert site_url(rel) == url

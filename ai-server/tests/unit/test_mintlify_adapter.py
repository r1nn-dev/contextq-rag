"""v1.x Mintlify Adapter — 골든 파일 테스트 (doc-source.md §4.2, 정책서 §4.3).

골든 파일을 다시 만들려면: `UPDATE_GOLDEN=1 uv run pytest tests/unit/test_mintlify_adapter.py`
(다시 만든 뒤에는 diff를 직접 검토한다)
"""

import json
import os
from dataclasses import asdict
from pathlib import Path

import pytest

from src.adapters.base import AdapterContext, create_adapter
from src.adapters.markdown import Line, to_lines
from src.adapters.mintlify import (
    apply_conditional_blocks,
    is_included,
    replace_api_refs,
    site_url,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "mintlify"
GOLDEN = FIXTURES / "expected.json"


def _run() -> tuple[list[dict[str, object]], dict[str, object]]:
    adapter = create_adapter("MintlifyAdapter", AdapterContext(doc_path="src/oss/"))
    documents = [asdict(d) for d in adapter.iter_documents(FIXTURES)]
    return documents, asdict(adapter.report)


def test_golden_output() -> None:
    documents, report = _run()
    actual = json.loads(json.dumps({"documents": documents, "report": report}))
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN.write_text(json.dumps(actual, ensure_ascii=False, indent=2) + "\n", "utf-8")
    assert actual == json.loads(GOLDEN.read_text("utf-8"))


def test_no_js_blocks_or_markers_remain() -> None:
    documents, _ = _run()
    texts = [s["text"] for d in documents for s in d["sections"]]  # type: ignore[union-attr]
    assert not any("createAgent" in t or "JavaScript readers" in t for t in texts)
    assert not any(line.startswith(":::") for t in texts for line in t.split("\n"))


def test_missing_snippet_is_reported_not_rendered() -> None:
    documents, report = _run()
    assert report["snippet_references"] == 2
    assert report["missing_snippets"] == [
        {
            "file_path": "src/oss/langchain/agents.mdx",
            "component": "AgentsMissingPy",
            "import_path": "/snippets/code-samples/agents-missing-py.mdx",
        }
    ]
    assert report["empty_documents"] == ["src/oss/langchain/retrieval.mdx"]


@pytest.mark.parametrize(
    ("rel", "included"),
    [
        ("langchain/agents.mdx", True),
        ("langchain/errors/MODEL_NOT_FOUND.mdx", True),
        ("concepts/memory.mdx", True),
        ("python/migrate/langchain-v1.mdx", True),
        ("versioning.mdx", True),
        ("langchain/frontend/overview.mdx", False),
        ("langchain/changelog-py.mdx", False),
        ("python/migrate/langgraph-v1.mdx", False),
        ("javascript/langchain/agents.mdx", False),
        ("langgraph/overview.mdx", False),
        ("python/integrations/providers/openai.mdx", False),
    ],
)
def test_include_exclude_paths(rel: str, included: bool) -> None:
    assert is_included(rel) is included


def test_site_url() -> None:
    assert (
        site_url("langchain/agents.mdx") == "https://docs.langchain.com/oss/python/langchain/agents"
    )
    assert (
        site_url("python/migrate/langchain-v1.mdx")
        == "https://docs.langchain.com/oss/python/migrate/langchain-v1"
    )


def test_conditional_blocks_keep_line_numbers() -> None:
    lines = to_lines(":::python\npy\n:::\n:::js\njs\n:::\n:::other\nkept\n:::")
    assert apply_conditional_blocks(lines) == [Line(2, "py"), Line(8, "kept")]


def test_api_refs() -> None:
    lines = to_lines("@[`create_agent`] and @[interrupt]\n```\n@[`x`]\n```")
    assert [line.text for line in replace_api_refs(lines)] == [
        "`create_agent` and interrupt",
        "```",
        "@[`x`]",
        "```",
    ]

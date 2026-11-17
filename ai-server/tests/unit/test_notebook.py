"""`.ipynb` 직렬화 — 셀 순서, 출력 셀 제외, code 셀 펜스 (doc-source.md §4.3)."""

import json

import pytest

from src.adapters.notebook import NotebookFormatError, serialize_notebook


def _nb(*cells: dict[str, object]) -> str:
    return json.dumps({"cells": list(cells), "metadata": {}, "nbformat": 4})


def test_cells_serialized_in_order_without_outputs() -> None:
    raw = _nb(
        {"cell_type": "raw", "source": ["---\n", "sidebar_position: 2\n", "---"]},
        {"cell_type": "markdown", "source": ["# How to call tools\n", "\n", "Intro text."]},
        {
            "cell_type": "code",
            "source": ["%pip install -qU langchain\n", "print('hi')"],
            "outputs": [{"output_type": "stream", "text": ["OUTPUT_SHOULD_NOT_APPEAR"]}],
        },
        {"cell_type": "markdown", "source": "   "},
        {"cell_type": "markdown", "source": "## Next"},
    )
    assert serialize_notebook(raw) == (
        "---\nsidebar_position: 2\n---\n\n"
        "# How to call tools\n\nIntro text.\n\n"
        "```python\n%pip install -qU langchain\nprint('hi')\n```\n\n"
        "## Next"
    )


def test_crlf_sources_are_normalized() -> None:
    raw = _nb({"cell_type": "markdown", "source": ["a\r\n", "b"]})
    assert serialize_notebook(raw) == "a\nb"


@pytest.mark.parametrize("raw", ["not json", "{}", "[]"])
def test_invalid_notebook_raises(raw: str) -> None:
    with pytest.raises(NotebookFormatError):
        serialize_notebook(raw)

"""정규화 문서 모델과 Adapter 레지스트리."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from src.adapters.base import (
    AdapterContext,
    AdapterNotRegisteredError,
    AdapterReport,
    MissingSnippet,
    create_adapter,
    register_adapter,
)
from src.domain.documents import NormalizedDocument, Section


def test_section_line_range() -> None:
    section = Section("A > B", "## B\n\nbody", (10, 11, 12))
    assert (section.line_start, section.line_end) == (10, 12)


def test_section_rejects_mismatched_line_numbers() -> None:
    with pytest.raises(ValueError):
        Section("A", "one\ntwo", (1,))


def test_unknown_adapter_raises() -> None:
    with pytest.raises(AdapterNotRegisteredError):
        create_adapter("NoSuchAdapter", AdapterContext(doc_path="docs/"))


def test_registered_adapter_is_created() -> None:
    class _Fake:
        def __init__(self, context: AdapterContext) -> None:
            self.context = context
            self.report = AdapterReport()

        def iter_documents(self, root: Path) -> Iterator[NormalizedDocument]:
            return iter(())

    register_adapter("FakeAdapter")(_Fake)
    adapter = create_adapter("FakeAdapter", AdapterContext(doc_path="docs/"))
    assert isinstance(adapter, _Fake)
    assert adapter.context.doc_path == "docs/"


def test_report_counts() -> None:
    report = AdapterReport()
    report.count_file("mdx")
    report.count_file("mdx")
    report.missing_snippets += [
        MissingSnippet("a.mdx", "X", "/snippets/x.mdx"),
        MissingSnippet("a.mdx", "Y", "/snippets/y.mdx"),
    ]
    assert report.files_read == 2
    assert report.files_by_type == {"mdx": 2}
    assert report.files_with_missing_snippets == 1

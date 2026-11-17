"""v0.3 Docusaurus Source Adapter — doc-source.md §4.3, 정책서 §4.3.

`.md`·`.mdx`는 admonition 마커를 지운 뒤 공통 전처리를 적용한다.
`.ipynb`는 셀 순서대로 직렬화(출력 셀 제외)한 텍스트에 같은 전처리를 적용한다.
"""

import re
from collections.abc import Iterator
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath

from src.adapters.base import AdapterContext, AdapterReport, register_adapter
from src.adapters.markdown import (
    Line,
    build_sections,
    collapse_blank_lines,
    fence_mask,
    first_h1,
    remove_mdx_statements,
    strip_frontmatter,
    strip_jsx,
    to_lines,
)
from src.adapters.notebook import serialize_notebook
from src.domain.documents import NormalizedDocument

SITE_BASE = "https://python.langchain.com/v0.3/docs/"
SUFFIXES = {".md": "md", ".mdx": "mdx", ".ipynb": "ipynb"}

# docs/specs/data-sources.md §3.1 포함·제외 경로 (문서 루트 docs/docs/ 기준)
INCLUDE = (
    "concepts/**",
    "how_to/**",
    "tutorials/**",
    "versions/**",
    "troubleshooting/**",
    "introduction.mdx",
)
EXCLUDE: tuple[str, ...] = ()  # integrations/** 등은 INCLUDE에 없으므로 읽지 않는다

_ADMONITION_OPEN = re.compile(
    r"^\s*:::\s*(note|tip|info|important|warning|caution|danger)(?:\[([^\]]*)\])?\s*(.*)$"
)
_ADMONITION_CLOSE = re.compile(r"^\s*:::\s*$")


def is_included(rel_path: str) -> bool:
    return any(fnmatchcase(rel_path, p) for p in INCLUDE) and not any(
        fnmatchcase(rel_path, p) for p in EXCLUDE
    )


def site_url(rel_path: str) -> str:
    path = PurePosixPath(rel_path).with_suffix("")
    if path.name == "index":
        path = path.parent
    stem = "" if str(path) == "." else f"{path}/"
    return SITE_BASE + stem


def strip_admonitions(lines: list[Line]) -> list[Line]:
    """admonition 마커 줄을 지우고 제목(`:::info 제목`, `:::tip[제목]`)은 텍스트로 남긴다."""
    mask = fence_mask(lines)
    out: list[Line] = []
    for line, in_fence in zip(lines, mask, strict=True):
        if not in_fence:
            opened = _ADMONITION_OPEN.match(line.text)
            if opened:
                title = (opened.group(2) or opened.group(3) or "").strip()
                if title:
                    out.append(Line(line.no, title))
                continue
            if _ADMONITION_CLOSE.match(line.text):
                continue
        out.append(line)
    return out


class DocusaurusAdapter:
    def __init__(self, context: AdapterContext) -> None:
        self.doc_path = context.doc_path.strip("/")
        self.report = AdapterReport()

    def iter_documents(self, root: Path) -> Iterator[NormalizedDocument]:
        doc_root = root / self.doc_path
        for path in sorted(doc_root.rglob("*")):
            doc_type = SUFFIXES.get(path.suffix)
            rel = path.relative_to(doc_root).as_posix()
            if doc_type is None or not path.is_file() or not is_included(rel):
                continue
            raw = path.read_text(encoding="utf-8")
            document = self.parse(rel, raw, doc_type)
            self.report.count_file(doc_type)
            if document.sections:
                yield document
            else:
                self.report.empty_documents.append(document.file_path)

    def parse(self, rel: str, raw: str, doc_type: str) -> NormalizedDocument:
        text = serialize_notebook(raw) if doc_type == "ipynb" else raw
        title, lines = strip_frontmatter(to_lines(text))
        lines = strip_admonitions(lines)
        lines = remove_mdx_statements(lines)
        lines = collapse_blank_lines(strip_jsx(lines))
        title = title or first_h1(lines) or PurePosixPath(rel).stem.replace("_", " ").title()
        return NormalizedDocument(
            file_path=f"{self.doc_path}/{rel}",
            title=title,
            doc_type=doc_type,
            site_url=site_url(rel),
            sections=tuple(build_sections(lines, title)),
        )


register_adapter("DocusaurusAdapter")(DocusaurusAdapter)

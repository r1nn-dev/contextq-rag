"""v1.x Mintlify Source Adapter — doc-source.md §4.2, 정책서 §4.3.

처리 순서: frontmatter → 스니펫 import 수집 → `:::js`/`:::python` → 스니펫 펼침
→ import·export 제거 → API 참조 → JSX 제거 → 빈 줄 정리 → 섹션 분리.
`:::js` 블록을 먼저 지워야 JS 전용 스니펫이 펼쳐지거나 누락으로 잡히지 않는다.
"""

import re
from collections.abc import Iterator
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath

from src.adapters.base import (
    AdapterContext,
    AdapterReport,
    MissingSnippet,
    register_adapter,
)
from src.adapters.markdown import (
    Line,
    build_sections,
    collapse_blank_lines,
    fence_mask,
    remove_mdx_statements,
    strip_frontmatter,
    strip_jsx,
    to_lines,
)
from src.domain.documents import NormalizedDocument

SITE_BASE = "https://docs.langchain.com/oss/python/"
SNIPPET_ROOT = "src"  # import 경로 "/snippets/…" → 저장소의 "src/snippets/…"
MAX_SNIPPET_DEPTH = 3  # 스니펫 안의 스니펫 import 허용 깊이

# docs/specs/data-sources.md §3.2 포함·제외 경로 (문서 루트 src/oss/ 기준)
INCLUDE = (
    "langchain/**",
    "concepts/**",
    "python/migrate/langchain-v1.mdx",
    "common-errors.mdx",
    "versioning.mdx",
    "release-policy.mdx",
)
EXCLUDE = (
    "langchain/frontend/**",
    "langchain/changelog-*.mdx",
)

_SNIPPET_IMPORT = re.compile(r"^import\s+(\w+)\s+from\s+['\"](/snippets/[^'\"]+)['\"]")
_SNIPPET_TAG = re.compile(r"^\s*<(\w+)\s*/>\s*$")
_CONDITION_OPEN = re.compile(r"^:::(\w+)\s*$")
_CONDITION_CLOSE = re.compile(r"^:::\s*$")
_API_REF = re.compile(r"@\[([^\]\n]+)\]")
_DROPPED_LANGUAGES = {"js"}  # 정책서 §3.2 수집 언어: Python만


def is_included(rel_path: str) -> bool:
    return any(fnmatchcase(rel_path, p) for p in INCLUDE) and not any(
        fnmatchcase(rel_path, p) for p in EXCLUDE
    )


def site_url(rel_path: str) -> str:
    stem = str(PurePosixPath(rel_path).with_suffix(""))
    return SITE_BASE + stem.removeprefix("python/")


def collect_snippet_imports(lines: list[Line]) -> dict[str, str]:
    mask = fence_mask(lines)
    imports: dict[str, str] = {}
    for line, in_fence in zip(lines, mask, strict=True):
        match = None if in_fence else _SNIPPET_IMPORT.match(line.text)
        if match:
            imports[match.group(1)] = match.group(2)
    return imports


def apply_conditional_blocks(lines: list[Line]) -> list[Line]:
    """`:::js` 블록은 내용까지, 그 밖의 `:::lang` 블록은 마커 줄만 지운다."""
    mask = fence_mask(lines)
    out: list[Line] = []
    dropping = False
    inside = False
    for line, in_fence in zip(lines, mask, strict=True):
        if not in_fence:
            stripped = line.text.strip()
            opened = _CONDITION_OPEN.match(stripped)
            if opened and not inside:
                inside = True
                dropping = opened.group(1) in _DROPPED_LANGUAGES
                continue
            if _CONDITION_CLOSE.match(stripped) and inside:
                inside = dropping = False
                continue
        if not dropping:
            out.append(line)
    return out


def replace_api_refs(lines: list[Line]) -> list[Line]:
    """`@[`name`]` → `` `name` ``, `@[name]` → `name` (펜스 밖)."""
    mask = fence_mask(lines)
    return [
        line if in_fence else Line(line.no, _API_REF.sub(r"\1", line.text))
        for line, in_fence in zip(lines, mask, strict=True)
    ]


class MintlifyAdapter:
    def __init__(self, context: AdapterContext) -> None:
        self.doc_path = context.doc_path.strip("/")
        self.report = AdapterReport()

    def iter_documents(self, root: Path) -> Iterator[NormalizedDocument]:
        doc_root = root / self.doc_path
        for path in sorted(doc_root.rglob("*.mdx")):
            rel = path.relative_to(doc_root).as_posix()
            if not is_included(rel):
                continue
            document = self.parse(root, rel, path.read_text(encoding="utf-8"))
            self.report.count_file("mdx")
            if document.sections:
                yield document
            else:
                self.report.empty_documents.append(document.file_path)

    def parse(self, root: Path, rel: str, raw: str) -> NormalizedDocument:
        file_path = f"{self.doc_path}/{rel}"
        title, lines = strip_frontmatter(to_lines(raw))
        lines = self._expand_snippets(root, file_path, apply_conditional_blocks(lines), depth=0)
        lines = remove_mdx_statements(lines)
        lines = replace_api_refs(lines)
        lines = collapse_blank_lines(strip_jsx(lines))
        title = title or PurePosixPath(rel).stem.replace("-", " ").title()
        return NormalizedDocument(
            file_path=file_path,
            title=title,
            doc_type="mdx",
            site_url=site_url(rel),
            sections=tuple(build_sections(lines, title)),
        )

    def _expand_snippets(
        self, root: Path, file_path: str, lines: list[Line], *, depth: int
    ) -> list[Line]:
        imports = collect_snippet_imports(lines)
        if not imports:
            return lines
        mask = fence_mask(lines)
        out: list[Line] = []
        for line, in_fence in zip(lines, mask, strict=True):
            tag = None if in_fence else _SNIPPET_TAG.match(line.text)
            if not tag or tag.group(1) not in imports:
                out.append(line)
                continue
            component, import_path = tag.group(1), imports[tag.group(1)]
            if depth == 0:
                self.report.snippet_references += 1
            snippet = root / SNIPPET_ROOT / import_path.lstrip("/")
            if depth >= MAX_SNIPPET_DEPTH or not snippet.is_file():
                if depth == 0:
                    self.report.missing_snippets.append(
                        MissingSnippet(file_path, component, import_path)
                    )
                continue
            _, body = strip_frontmatter(to_lines(snippet.read_text(encoding="utf-8")))
            body = apply_conditional_blocks(body)
            body = self._expand_snippets(root, file_path, body, depth=depth + 1)
            # 펼친 줄은 태그 줄의 원문 라인 번호를 갖는다 (doc-source.md §4.2)
            out.extend(Line(line.no, b.text) for b in body)
        return out


register_adapter("MintlifyAdapter")(MintlifyAdapter)

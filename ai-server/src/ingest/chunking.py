"""청킹 전략 A·B·C — interfaces.md §4 `DocumentChunker`, doc-source.md §6.

청크는 섹션(전략 C는 H2 묶음) 경계를 넘지 않고, 원문 라인 범위를 가진다.
"""

import re
from typing import Any, Protocol, TypedDict

from langchain_text_splitters import (
    CharacterTextSplitter,
    RecursiveCharacterTextSplitter,
    TextSplitter,
)

from src.adapters.markdown import fence_mask, to_lines
from src.config.ingest_config import Strategy
from src.domain.documents import NormalizedDocument, Section

_FENCE_LINE = re.compile(r"^\s*(`{3,}|~{3,})")


class Chunk(TypedDict):
    content: str
    heading_path: str
    line_start: int  # 원문 라인 번호
    line_end: int


class ChunkingError(Exception):
    """분할 처리 실패 — 해당 문서는 건너뛰고 로그를 남긴다 (interfaces.md §5)."""


class DocumentChunker(Protocol):
    def chunk(self, document: NormalizedDocument) -> list[Chunk]: ...


def line_range(section: Section, start: int, length: int) -> tuple[int, int]:
    """section.text의 문자 구간 [start, start+length)이 걸친 원문 라인 범위."""
    first = section.text.count("\n", 0, start)
    last = section.text.count("\n", 0, max(start + length - 1, start))
    return section.line_numbers[first], section.line_numbers[last]


def splits_code_fence(content: str) -> bool:
    """펜스 줄 수가 홀수면 청크 경계가 코드 펜스를 가른 것이다 (A·B 사후 검사)."""
    return sum(1 for line in content.split("\n") if _FENCE_LINE.match(line)) % 2 == 1


def _require_sections(document: NormalizedDocument) -> None:
    if not document.sections:
        raise ChunkingError(f"섹션이 없는 문서입니다: {document.file_path}")


class SplitterChunker:
    """전략 A·B — 섹션마다 LangChain 분할기를 적용한다."""

    def __init__(self, splitter: TextSplitter) -> None:
        self.splitter = splitter

    def chunk(self, document: NormalizedDocument) -> list[Chunk]:
        _require_sections(document)
        chunks: list[Chunk] = []
        for section in document.sections:
            cursor = 0
            for piece in self.splitter.create_documents([section.text]):
                content = piece.page_content
                start = int(piece.metadata.get("start_index", -1))
                if start < 0:
                    start = section.text.find(content, cursor)
                if start < 0:
                    raise ChunkingError(f"청크 위치를 찾지 못했습니다: {document.file_path}")
                cursor = start
                line_start, line_end = line_range(section, start, len(content))
                chunks.append(
                    Chunk(
                        content=content,
                        heading_path=section.heading_path,
                        line_start=line_start,
                        line_end=line_end,
                    )
                )
        return chunks


def group_sections(sections: tuple[Section, ...], header_depth: int) -> list[Section]:
    """heading_path 깊이가 header_depth보다 깊은 섹션을 바로 앞 묶음에 이어 붙인다 (전략 C)."""
    groups: list[Section] = []
    for section in sections:
        depth = section.heading_path.count(" > ") + 1
        if groups and depth > header_depth:
            head = groups[-1]
            groups[-1] = Section(
                head.heading_path,
                f"{head.text}\n{section.text}",
                head.line_numbers + section.line_numbers,
            )
        else:
            groups.append(section)
    return groups


def _blocks(lines: list[str]) -> list[tuple[int, int]]:
    """펜스 밖 빈 줄로 나눈 문단 블록 [start, end] 목록. 코드 펜스는 한 블록 안에 남는다."""
    mask = fence_mask(to_lines("\n".join(lines)))
    blocks: list[tuple[int, int]] = []
    start: int | None = None
    for i, (text, in_fence) in enumerate(zip(lines, mask, strict=True)):
        if not in_fence and not text.strip():
            if start is not None:
                blocks.append((start, i - 1))
                start = None
        elif start is None:
            start = i
    if start is not None:
        blocks.append((start, len(lines) - 1))
    return blocks


class StructureChunker:
    """전략 C — H2 묶음을 문단 경계로 나누고, 코드 펜스는 쪼개지 않는다."""

    def __init__(self, chunk_size: int, header_depth: int) -> None:
        self.chunk_size = chunk_size
        self.header_depth = header_depth

    def chunk(self, document: NormalizedDocument) -> list[Chunk]:
        _require_sections(document)
        chunks: list[Chunk] = []
        for group in group_sections(document.sections, self.header_depth):
            lines = group.text.split("\n")
            for first, last in self._pack(lines):
                chunks.append(
                    Chunk(
                        content="\n".join(lines[first : last + 1]),
                        heading_path=group.heading_path,
                        line_start=group.line_numbers[first],
                        line_end=group.line_numbers[last],
                    )
                )
        return chunks

    def _size(self, lines: list[str], first: int, last: int) -> int:
        return len("\n".join(lines[first : last + 1]))

    def _pack(self, lines: list[str]) -> list[tuple[int, int]]:
        """문단 블록을 상한까지 이어 담는다. 상한을 넘는 단일 블록은 그대로 한 청크다."""
        ranges: list[tuple[int, int]] = []
        current: tuple[int, int] | None = None
        for first, last in _blocks(lines):
            if current is None:
                current = (first, last)
            elif self._size(lines, current[0], last) <= self.chunk_size:
                current = (current[0], last)
            else:
                ranges.append(current)
                current = (first, last)
        if current is not None:
            ranges.append(current)
        return ranges


def make_chunker(strategy: Strategy, params: dict[str, Any]) -> DocumentChunker:
    if strategy == "A":
        return SplitterChunker(
            CharacterTextSplitter(
                separator=params["separator"],
                chunk_size=params["chunk_size"],
                chunk_overlap=params["chunk_overlap"],
                add_start_index=True,
            )
        )
    if strategy == "B":
        return SplitterChunker(
            RecursiveCharacterTextSplitter(
                separators=params["separators"],
                chunk_size=params["chunk_size"],
                chunk_overlap=params["chunk_overlap"],
                add_start_index=True,
            )
        )
    if strategy == "C":
        return StructureChunker(
            chunk_size=params["chunk_size"], header_depth=len(params["header_levels"])
        )
    raise ChunkingError(f"지원하지 않는 청킹 전략입니다: {strategy}")

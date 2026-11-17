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
    raise ChunkingError(f"지원하지 않는 청킹 전략입니다: {strategy}")

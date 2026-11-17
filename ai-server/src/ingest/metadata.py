"""청크 메타데이터 조립 — 정책서 §4.1·§4.2, doc-source.md §7, ADR-007.

- `chunk_id`: 같은 입력이면 같은 ID (INV-04).
  필드는 단위 구분자(U+001F)로 이어 경계가 섞이지 않게 한다.
- `permalink`: 40자 커밋 SHA를 포함한 URL만 만든다 (INV-05). `.ipynb`는 파일 단위.
"""

import hashlib
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import TypedDict

import tiktoken

from src.domain.documents import NormalizedDocument
from src.ingest.chunking import Chunk

_SHA = re.compile(r"^[0-9a-f]{40}$")
_FENCE_LINE = re.compile(r"^\s*(`{3,}|~{3,})", re.MULTILINE)
TOKEN_ENCODING = "cl100k_base"


class ChunkMetadata(TypedDict):
    """Chroma 저장 메타데이터 — 정책서 §4.2 필수 필드 (interfaces.md §2.1)."""

    chunk_id: str
    source_key: str
    framework: str
    version: str
    ingest_run_id: int
    commit_sha: str
    file_path: str
    heading_path: str
    line_start: int
    line_end: int
    permalink: str
    site_url: str
    doc_type: str
    chunk_strategy: str
    chunk_params_hash: str
    embedding_model: str
    token_count: int
    has_code: bool


REQUIRED_FIELDS: tuple[str, ...] = tuple(ChunkMetadata.__annotations__)


class InvalidPermalinkError(ValueError):
    """커밋 SHA가 아닌 ref(브랜치명 등)로 permalink를 만들려 함 (INV-05)."""


@dataclass(frozen=True)
class RunContext:
    source_key: str
    framework: str
    version: str  # ai.sources.version_label
    ingest_run_id: int
    commit_sha: str
    repo: str  # "owner/name"
    chunk_strategy: str
    chunk_params_hash: str
    embedding_model: str


@dataclass(frozen=True)
class PreparedChunk:
    chunk_id: str
    content: str
    metadata: ChunkMetadata


def make_chunk_id(ctx: RunContext, file_path: str, heading_path: str, chunk_index: int) -> str:
    parts = [
        ctx.source_key,
        ctx.commit_sha,
        file_path,
        heading_path,
        str(chunk_index),
        ctx.chunk_strategy,
        ctx.chunk_params_hash,
    ]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:32]


def make_permalink(
    repo: str, commit_sha: str, file_path: str, doc_type: str, line_start: int, line_end: int
) -> str:
    if not _SHA.match(commit_sha):
        raise InvalidPermalinkError(f"40자 커밋 SHA가 아닙니다: {commit_sha!r}")
    base = f"https://github.com/{repo}/blob/{commit_sha}/{file_path}"
    if doc_type == "ipynb":
        return base
    return f"{base}?plain=1#L{line_start}-L{line_end}"


@lru_cache
def _encoder() -> tiktoken.Encoding:
    return tiktoken.get_encoding(TOKEN_ENCODING)


def count_tokens(text: str) -> int:
    return len(_encoder().encode(text, disallowed_special=()))


def assemble(
    ctx: RunContext, document: NormalizedDocument, chunks: list[Chunk]
) -> list[PreparedChunk]:
    """문서의 청크에 파일 안 순서(chunk_index)를 매기고 필수 메타데이터를 붙인다."""
    prepared: list[PreparedChunk] = []
    for index, chunk in enumerate(chunks):
        chunk_id = make_chunk_id(ctx, document.file_path, chunk["heading_path"], index)
        metadata = ChunkMetadata(
            chunk_id=chunk_id,
            source_key=ctx.source_key,
            framework=ctx.framework,
            version=ctx.version,
            ingest_run_id=ctx.ingest_run_id,
            commit_sha=ctx.commit_sha,
            file_path=document.file_path,
            heading_path=chunk["heading_path"],
            line_start=chunk["line_start"],
            line_end=chunk["line_end"],
            permalink=make_permalink(
                ctx.repo,
                ctx.commit_sha,
                document.file_path,
                document.doc_type,
                chunk["line_start"],
                chunk["line_end"],
            ),
            site_url=document.site_url,
            doc_type=document.doc_type,
            chunk_strategy=ctx.chunk_strategy,
            chunk_params_hash=ctx.chunk_params_hash,
            embedding_model=ctx.embedding_model,
            token_count=count_tokens(chunk["content"]),
            has_code=bool(_FENCE_LINE.search(chunk["content"])),
        )
        prepared.append(PreparedChunk(chunk_id, chunk["content"], metadata))
    return prepared

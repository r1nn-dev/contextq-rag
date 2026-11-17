"""청크 메타데이터 — 결정적 chunk_id(INV-04), SHA 고정 permalink(INV-05), 필수 필드(정책서 §4.2)."""

from dataclasses import replace
from pathlib import Path

import pytest

from src.adapters.base import AdapterContext, create_adapter
from src.config.ingest_config import load_chunking_config, params_hash
from src.ingest.chunking import make_chunker
from src.ingest.metadata import (
    REQUIRED_FIELDS,
    InvalidPermalinkError,
    RunContext,
    assemble,
    make_chunk_id,
    make_permalink,
)

SHA = "39276c943de9b4065ac86ceff57c73903cc50e41"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CONFIG = load_chunking_config()


def _context(strategy: str = "B") -> RunContext:
    return RunContext(
        source_key="langchain_v1x",
        framework="langchain",
        version="v1.x",
        ingest_run_id=13,
        commit_sha=SHA,
        repo="langchain-ai/docs",
        chunk_strategy=strategy,
        chunk_params_hash=params_hash(CONFIG.params(strategy)),  # type: ignore[arg-type]
        embedding_model="text-embedding-3-small",
    )


def _build(strategy: str = "B") -> list[dict[str, object]]:
    adapter = create_adapter("MintlifyAdapter", AdapterContext(doc_path="src/oss/"))
    chunker = make_chunker(strategy, CONFIG.params(strategy))  # type: ignore[arg-type]
    out = []
    for document in adapter.iter_documents(FIXTURES / "mintlify"):
        for prepared in assemble(_context(strategy), document, chunker.chunk(document)):
            out.append(dict(prepared.metadata))
    return out


def test_same_input_twice_gives_same_chunk_ids() -> None:
    first = [m["chunk_id"] for m in _build()]
    second = [m["chunk_id"] for m in _build()]
    assert first == second
    assert len(set(first)) == len(first)


def test_strategy_change_gives_different_ids() -> None:
    assert {m["chunk_id"] for m in _build("B")}.isdisjoint({m["chunk_id"] for m in _build("C")})


def test_chunk_id_depends_on_every_field() -> None:
    base = make_chunk_id(_context(), "a.mdx", "A > B", 0)
    assert len(base) == 32
    variants = [
        make_chunk_id(replace(_context(), commit_sha="f" * 40), "a.mdx", "A > B", 0),
        make_chunk_id(_context(), "b.mdx", "A > B", 0),
        make_chunk_id(_context(), "a.mdx", "A > C", 0),
        make_chunk_id(_context(), "a.mdx", "A > B", 1),
        make_chunk_id(replace(_context(), chunk_params_hash="00000000"), "a.mdx", "A > B", 0),
    ]
    assert base not in variants


@pytest.mark.parametrize("strategy", ["A", "B", "C"])
def test_required_fields_present_and_typed(strategy: str) -> None:
    for metadata in _build(strategy):
        assert set(metadata) == set(REQUIRED_FIELDS)
        assert all(value not in (None, "") for value in metadata.values())
        assert metadata["line_start"] <= metadata["line_end"]  # type: ignore[operator]
        assert metadata["token_count"] > 0  # type: ignore[operator]


def test_permalink_line_anchor_and_notebook() -> None:
    assert make_permalink("o/r", SHA, "src/oss/a.mdx", "mdx", 120, 168) == (
        f"https://github.com/o/r/blob/{SHA}/src/oss/a.mdx?plain=1#L120-L168"
    )
    assert make_permalink("o/r", SHA, "docs/docs/a.ipynb", "ipynb", 1, 9) == (
        f"https://github.com/o/r/blob/{SHA}/docs/docs/a.ipynb"
    )


@pytest.mark.parametrize("ref", ["main", "v0.3", SHA[:7], ""])
def test_permalink_rejects_branch_or_short_ref(ref: str) -> None:
    with pytest.raises(InvalidPermalinkError):
        make_permalink("o/r", ref, "a.mdx", "mdx", 1, 2)

"""버전 격리 검색 — ACTIVE 컬렉션 지정(1차 격리)·run 고정·질의 임베딩 (ADR-004, 정책서 §5.3)."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import openai
import pytest

from src.config.ingest_config import load_embedding_config
from src.ingest.embedder import EmbeddingError
from src.ingest.store import ChromaVectorStore
from src.retrieval.embedding import OpenAIQueryEmbedder
from src.retrieval.errors import EmbeddingModelMismatchError, IndexNotActiveError
from src.retrieval.pointers import ActiveIndex, StaticPointers
from src.retrieval.search import ChromaRetriever

V1X, V03 = "langchain_v1x", "langchain_v03"
MODEL = "text-embedding-3-small"


def meta(source_key: str, run_id: int, i: int, **overrides: Any) -> dict[str, Any]:
    version = "v1.x" if source_key == V1X else "v0.3"
    return {
        "chunk_id": f"{source_key}-r{run_id}-{i}",
        "source_key": source_key,
        "version": version,
        "ingest_run_id": run_id,
        "embedding_model": MODEL,
        "file_path": f"docs/{i}.mdx",
        "heading_path": f"Doc > S{i}",
        "token_count": 100 + i,
        "permalink": f"https://github.com/o/r/blob/{'a' * 40}/docs/{i}.mdx",
        "site_url": f"https://docs.example.com/{i}",
        **overrides,
    }


def add_collection(
    store: ChromaVectorStore,
    source_key: str,
    run_id: int,
    vectors: list[list[float]],
    metas: list[dict[str, Any]] | None = None,
    *,
    model: str = MODEL,
) -> str:
    name = f"{source_key}_run{run_id}"
    store.create_collection(name, {"embedding_model": model, "embedding_dim": 3})
    store.add(
        name,
        ids=[f"{source_key}-r{run_id}-{i}" for i in range(len(vectors))],
        embeddings=vectors,
        documents=[f"{source_key} run{run_id} chunk {i}" for i in range(len(vectors))],
        metadatas=metas or [meta(source_key, run_id, i) for i in range(len(vectors))],
    )
    return name


def index(source_key: str = V1X, run_id: int = 3) -> ActiveIndex:
    version = "v1.x" if source_key == V1X else "v0.3"
    return ActiveIndex(source_key, version, run_id, "a" * 40, None, None, MODEL)


class FakeQueryEmbedder:
    def __init__(self, vectors: dict[str, list[float]], model: str = MODEL) -> None:
        self.vectors = vectors
        self.model = model
        self.calls: list[str] = []

    def embed_query(self, text: str) -> list[float]:
        self.calls.append(text)
        return self.vectors[text]


class SwitchablePointers:
    def __init__(self, active: ActiveIndex) -> None:
        self.active = active

    def get(self, source_key: str) -> ActiveIndex:
        return self.active


@pytest.fixture()
def store(tmp_path: Path) -> ChromaVectorStore:
    store = ChromaVectorStore(tmp_path / "chroma")
    add_collection(store, V1X, 3, [[1.0, 0.0, 0.0], [0.6, 0.8, 0.0], [0.0, 0.0, 1.0]])
    # 같은 소스의 다른 run(직전 ACTIVE)과 다른 소스 — 질의와 더 가깝게 만든다
    add_collection(store, V1X, 2, [[0.99, 0.01, 0.0]])
    add_collection(store, V03, 1, [[1.0, 0.0, 0.0]])
    return store


EMBEDDER = FakeQueryEmbedder({"q": [1.0, 0.0, 0.0]})


def test_searches_only_the_active_run_collection(store: ChromaVectorStore) -> None:
    retriever = ChromaRetriever(store, StaticPointers({V1X: index()}), EMBEDDER)

    chunks = retriever.retrieve("q", V1X, top_k=5)

    assert [c["chunk_id"] for c in chunks] == [f"{V1X}-r3-0", f"{V1X}-r3-1", f"{V1X}-r3-2"]
    assert {c["source_key"] for c in chunks} == {V1X}
    assert chunks[0]["similarity"] == pytest.approx(1.0)
    assert [c["similarity"] for c in chunks] == sorted(
        (c["similarity"] for c in chunks), reverse=True
    )
    assert chunks[0]["site_url"] == "https://docs.example.com/0"
    assert chunks[0]["token_count"] == 100


def test_request_keeps_the_run_resolved_at_start(store: ChromaVectorStore) -> None:
    pointers = SwitchablePointers(index(run_id=3))
    retriever = ChromaRetriever(store, pointers, EMBEDDER)
    pinned = retriever.resolve(V1X)

    pointers.active = index(run_id=2)  # 요청 처리 중 활성화로 포인터 교체
    result = retriever.search("q", V1X, top_k=2, index=pinned)

    assert result.index.run_id == 3
    assert all(c["chunk_id"].startswith(f"{V1X}-r3-") for c in result.chunks)
    assert retriever.search("q", V1X, top_k=1).index.run_id == 2  # 다음 요청은 새 run


def test_missing_collection_is_index_not_active(store: ChromaVectorStore) -> None:
    retriever = ChromaRetriever(store, StaticPointers({V1X: index(run_id=9)}), EMBEDDER)

    with pytest.raises(IndexNotActiveError):
        retriever.retrieve("q", V1X)


def test_pinned_index_must_match_source(store: ChromaVectorStore) -> None:
    retriever = ChromaRetriever(store, StaticPointers({}), EMBEDDER)

    with pytest.raises(ValueError):
        retriever.search("q", V1X, index=index(V03, 1))


@pytest.mark.parametrize(("query", "top_k"), [("  ", 5), ("q", 0), ("q", 21)])
def test_rejects_invalid_input(store: ChromaVectorStore, query: str, top_k: int) -> None:
    retriever = ChromaRetriever(store, StaticPointers({V1X: index()}), EMBEDDER)

    with pytest.raises(ValueError):
        retriever.retrieve(query, V1X, top_k=top_k)


def test_records_embed_and_retrieve_latency(store: ChromaVectorStore) -> None:
    ticks = iter([10.0, 10.08, 10.2])
    retriever = ChromaRetriever(
        store, StaticPointers({V1X: index()}), EMBEDDER, clock=lambda: next(ticks)
    )

    result = retriever.search("q", V1X, top_k=1)

    assert (result.embed_ms, result.retrieve_ms) == (80, 120)


# --- OpenAI 질의 임베딩 ------------------------------------------------------------


class _FakeEmbeddings:
    def __init__(self, dims: int = 3, error: Exception | None = None) -> None:
        self.dims = dims
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(data=[SimpleNamespace(index=0, embedding=[0.1] * self.dims)])


def _embedder(fake: _FakeEmbeddings) -> OpenAIQueryEmbedder:
    config = load_embedding_config().model_copy(update={"dimensions": 3})
    return OpenAIQueryEmbedder("", config, client=SimpleNamespace(embeddings=fake))


def test_query_embedder_calls_configured_model() -> None:
    fake = _FakeEmbeddings()

    assert _embedder(fake).embed_query("hello") == [0.1, 0.1, 0.1]
    assert fake.calls == [{"model": MODEL, "input": ["hello"]}]


def test_query_embedder_wraps_errors() -> None:
    error = openai.APIConnectionError(request=SimpleNamespace())  # type: ignore[arg-type]
    with pytest.raises(EmbeddingError):
        _embedder(_FakeEmbeddings(error=error)).embed_query("hello")
    with pytest.raises(EmbeddingError):
        _embedder(_FakeEmbeddings(dims=2)).embed_query("hello")
    with pytest.raises(EmbeddingError):
        _embedder(_FakeEmbeddings()).embed_query(" ")


def test_query_embedder_requires_api_key() -> None:
    with pytest.raises(EmbeddingError):
        OpenAIQueryEmbedder("", load_embedding_config())


def test_query_embedding_policy_values() -> None:
    config = load_embedding_config()

    assert (config.query_timeout_seconds, config.query_max_retries) == (5, 1)


# --- 2차 검증(INV-02)·임베딩 모델(INV-03) -------------------------------------------


@pytest.mark.parametrize(
    "contaminated",
    [
        {"source_key": V03},  # 다른 소스
        {"version": "v0.3"},  # 다른 버전
        {"ingest_run_id": 2},  # 같은 소스의 다른 run
    ],
)
def test_contaminated_chunk_is_discarded_and_logged(
    tmp_path: Path, contaminated: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    store = ChromaVectorStore(tmp_path / "chroma")
    metas = [meta(V1X, 3, 0), {**meta(V1X, 3, 1), **contaminated}, meta(V1X, 3, 2)]
    add_collection(store, V1X, 3, [[1.0, 0.0, 0.0], [0.9, 0.1, 0.0], [0.5, 0.5, 0.0]], metas)
    retriever = ChromaRetriever(store, StaticPointers({V1X: index()}), EMBEDDER)

    with caplog.at_level("ERROR", logger="src.retrieval.search"):
        result = retriever.search("q", V1X, top_k=3)

    assert [c["chunk_id"] for c in result.chunks] == [f"{V1X}-r3-0", f"{V1X}-r3-2"]
    assert result.discarded == 1
    [record] = caplog.records
    assert record.getMessage() == "retrieval_chunk_discarded"
    assert record.__dict__["invariant"] == "INV-02"
    assert record.__dict__["chunk_id"] == f"{V1X}-r3-1"


def test_clean_index_discards_nothing(
    store: ChromaVectorStore, caplog: pytest.LogCaptureFixture
) -> None:
    retriever = ChromaRetriever(store, StaticPointers({V1X: index()}), EMBEDDER)

    with caplog.at_level("ERROR"):
        result = retriever.search("q", V1X, top_k=3)

    assert result.discarded == 0
    assert not caplog.records  # E1-F 목표: INV-02 폐기 로그 0건


def test_collection_model_mismatch_rejects_search(tmp_path: Path) -> None:
    store = ChromaVectorStore(tmp_path / "chroma")
    add_collection(store, V1X, 3, [[1.0, 0.0, 0.0]], model="text-embedding-3-large")
    embedder = FakeQueryEmbedder({"q": [1.0, 0.0, 0.0]})
    retriever = ChromaRetriever(store, StaticPointers({V1X: index()}), embedder)

    with pytest.raises(EmbeddingModelMismatchError) as exc:
        retriever.retrieve("q", V1X)
    assert exc.value.code == "EMBEDDING_MODEL_MISMATCH"
    assert embedder.calls == []  # 임베딩 호출 전에 거부


def test_chunk_model_mismatch_rejects_search(tmp_path: Path) -> None:
    store = ChromaVectorStore(tmp_path / "chroma")
    metas = [meta(V1X, 3, 0, embedding_model="text-embedding-ada-002")]
    add_collection(store, V1X, 3, [[1.0, 0.0, 0.0]], metas)
    retriever = ChromaRetriever(store, StaticPointers({V1X: index()}), EMBEDDER)

    with pytest.raises(EmbeddingModelMismatchError):
        retriever.retrieve("q", V1X)

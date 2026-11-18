"""청킹 설정 로더와 파라미터 해시 (정책서 §4.1)."""

from src.config.ingest_config import embedding_model_name, load_chunking_config, params_hash


def test_chunking_config_matches_e2_protocol() -> None:
    config = load_chunking_config()
    assert config.default_strategy == "C"  # E2 확정
    assert config.params("A") == {"chunk_size": 1000, "chunk_overlap": 200, "separator": "\n\n"}
    assert config.params("B")["separators"] == ["\n\n", "\n", " "]
    assert config.params("C")["header_levels"] == ["#", "##"]


def test_params_hash_is_stable_and_order_independent() -> None:
    a = params_hash({"chunk_size": 1000, "chunk_overlap": 200})
    b = params_hash({"chunk_overlap": 200, "chunk_size": 1000})
    assert a == b
    assert len(a) == 8
    assert a != params_hash({"chunk_size": 1001, "chunk_overlap": 200})


def test_embedding_model_name() -> None:
    assert embedding_model_name() == "text-embedding-3-small"

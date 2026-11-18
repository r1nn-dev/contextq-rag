"""검색 설정(`configs/rag.yaml`)과 τ 덮어쓰기 — ADR-008, 정책서 §5.3."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config.rag_config import load_compare_model_config, load_rag_config
from src.config.settings import Settings
from src.pipeline.prompts import load_template


def test_repository_config_uses_confirmed_values() -> None:
    retrieval = load_rag_config().retrieval

    assert retrieval.top_k == 8  # E2 확정
    assert retrieval.context_budget_tokens == 3000
    assert retrieval.thresholds == {"langchain_v03": 0.29, "langchain_v1x": 0.34}  # E1 확정


def test_repository_stream_and_generation_values_follow_policy() -> None:
    config = load_rag_config()

    assert config.generation.prompt_version == "single_v2"
    assert config.generation.compare_prompt_version == "compare_v1"
    stream = config.stream
    assert (stream.heartbeat_seconds, stream.max_duration_seconds) == (10, 120)
    assert stream.max_concurrency == 20
    assert stream.compare_max_duration_seconds == 30  # 정책서 §2.1 비교 모드 전체 타임아웃


def test_repository_compare_model_follows_policy() -> None:
    compare = load_compare_model_config()

    # 정책서 §5.6: temperature 0 · max_tokens 1,500 · 파싱 실패 1회 재시도, 호출 오류는 재시도 없음
    assert (compare.temperature, compare.max_tokens) == (0, 1500)
    assert (compare.max_retries, compare.parse_retries) == (0, 1)
    assert compare.timeout_seconds < load_rag_config().stream.compare_max_duration_seconds
    assert compare.resolve_model(" gpt-x ") == "gpt-x"
    assert compare.resolve_model("") == "gpt-4o-mini"


def test_default_compare_prompt_exists() -> None:
    load_template(load_rag_config().generation.compare_prompt_version)


def test_tau_prefers_env_override() -> None:
    retrieval = load_rag_config().retrieval

    assert retrieval.tau("langchain_v1x") == 0.34
    assert retrieval.tau("langchain_v1x", {"langchain_v1x": 0.42}) == 0.42
    assert retrieval.tau("langchain_v03", {"langchain_v1x": 0.42}) == 0.29


def test_unregistered_source_is_a_config_error() -> None:
    with pytest.raises(KeyError, match="react_v18"):
        load_rag_config().retrieval.tau("react_v18")


REST = """
generation: {prompt_version: single_v1}
stream: {heartbeat_seconds: 10, max_duration_seconds: 120, max_concurrency: 20}
"""


def _write(tmp_path: Path, body: str) -> Path:
    (tmp_path / "rag.yaml").write_text(body + REST, encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize(
    "body",
    [
        "retrieval: {top_k: 0, context_budget_tokens: 3000, thresholds: {a: 0.3}}",
        "retrieval: {top_k: 5, context_budget_tokens: 3001, thresholds: {a: 0.3}}",
        "retrieval: {top_k: 5, context_budget_tokens: 3000, thresholds: {}}",
    ],
)
def test_rejects_out_of_policy_values(tmp_path: Path, body: str) -> None:
    with pytest.raises(ValidationError):
        load_rag_config.__wrapped__(_write(tmp_path, body))


def test_rejects_tau_outside_unit_range(tmp_path: Path) -> None:
    body = "retrieval: {top_k: 5, context_budget_tokens: 3000, thresholds: {a: 1.5}}"
    with pytest.raises(ValueError, match="τ"):
        load_rag_config.__wrapped__(_write(tmp_path, body))


def test_settings_tau_overrides_only_set_values() -> None:
    settings = Settings(_env_file=None, tau_langchain_v03=0.35)  # type: ignore[call-arg]

    assert settings.tau_overrides() == {"langchain_v03": 0.35}


def test_settings_rejects_invalid_tau() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, tau_langchain_v1x=1.2)  # type: ignore[call-arg]

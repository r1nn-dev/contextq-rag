"""서비스 검색·생성 설정 로더 — `configs/rag.yaml`(ADR-008, 정책서 §5.3)·`models.yaml`.

`models.yaml`의 `llm`은 단일 모드 생성, `rewrite`는 멀티턴 질의 재작성(정책서 §5.2),
`compare`는 비교 모드 구조화 출력(정책서 §5.6) 파라미터다.

τ는 source_key별 값이고 `Settings`의 `TAU_{SOURCE_KEY}` 덮어쓰기가 우선한다.
"""

from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from src.config.ingest_config import CONFIG_DIR

CONTEXT_BUDGET_CAP = 3000  # 정책서 §5.3 컨텍스트 예산 3,000 고정 (eval/decision_rules.md §4)


class RetrievalConfig(BaseModel):
    top_k: int = Field(ge=1, le=20)
    context_budget_tokens: int = Field(gt=0, le=CONTEXT_BUDGET_CAP)
    thresholds: dict[str, float] = Field(min_length=1)

    def tau(self, source_key: str, overrides: Mapping[str, float] | None = None) -> float:
        """소스의 τ. 환경 변수 덮어쓰기 → yaml 순서. 등록되지 않은 소스는 설정 오류다."""
        if overrides and source_key in overrides:
            return overrides[source_key]
        try:
            return self.thresholds[source_key]
        except KeyError:
            raise KeyError(
                f"configs/rag.yaml retrieval.thresholds에 {source_key}가 없습니다"
            ) from None


class GenerationConfig(BaseModel):
    prompt_version: str = Field(min_length=1)  # 요청에 promptVersion이 없을 때
    compare_prompt_version: str = Field(default="compare_v1", min_length=1)  # 비교 모드 기본값


class StreamConfig(BaseModel):
    """정책서 §2.1 SSE 하트비트·단일 스트림 최대 시간·비교 모드 전체 시간, §8.1 동시 생성 상한."""

    heartbeat_seconds: float = Field(gt=0)
    max_duration_seconds: float = Field(gt=0)
    max_concurrency: int = Field(ge=1)
    compare_max_duration_seconds: float = Field(default=30, gt=0)


class RewriteConfig(BaseModel):
    """멀티턴 질의 재작성 규칙 (ADR-009, 정책서 §5.2)."""

    prompt_version: str = Field(default="rewrite_v2", min_length=1)
    history_turns: int = Field(default=3, ge=1)
    assistant_max_chars: int = Field(default=500, gt=0)
    max_output_chars: int = Field(default=200, gt=0, le=200)  # rewritten_query VARCHAR(200)

    @property
    def history_messages(self) -> int:
        """참조할 메시지 수 — 한 턴은 질문·답변 2개."""
        return self.history_turns * 2


class RagConfig(BaseModel):
    retrieval: RetrievalConfig
    generation: GenerationConfig
    stream: StreamConfig
    rewrite: RewriteConfig = Field(default_factory=RewriteConfig)


class LlmConfig(BaseModel):
    """`configs/models.yaml` `llm` — 단일 모드 생성 파라미터 (정책서 §5.5·§2.1)."""

    model: str = Field(min_length=1)
    temperature: float = Field(ge=0, le=2)
    max_tokens: int = Field(gt=0)
    first_token_timeout_seconds: float = Field(gt=0)
    max_retries: int = Field(ge=0)

    def resolve_model(self, override: str = "") -> str:
        """`LLM_MODEL`이 있으면 그 값, 없으면 yaml 기본 모델."""
        return override.strip() or self.model


class RewriteModelConfig(BaseModel):
    """`configs/models.yaml` `rewrite` — 재작성 호출 파라미터 (정책서 §2.1 질의 재작성 3초)."""

    model: str = Field(min_length=1)
    temperature: float = Field(ge=0, le=2)
    max_tokens: int = Field(gt=0)
    timeout_seconds: float = Field(gt=0)
    max_retries: int = Field(ge=0)


class CompareModelConfig(BaseModel):
    """`configs/models.yaml` `compare` — 비교 모드 구조화 출력 호출 (정책서 §5.6).

    `max_retries`는 호출 오류 재시도(SDK), `parse_retries`는 파싱 실패 재시도다.
    """

    model: str = Field(min_length=1)
    temperature: float = Field(ge=0, le=2)
    max_tokens: int = Field(gt=0)
    timeout_seconds: float = Field(gt=0)
    max_retries: int = Field(ge=0)
    parse_retries: int = Field(ge=0, le=1)  # 정책서 §5.6 "1회 재시도"

    def resolve_model(self, override: str = "") -> str:
        """`LLM_MODEL`이 있으면 그 값, 없으면 yaml 기본 모델."""
        return override.strip() or self.model


def _load(config_dir: Path, name: str = "rag.yaml") -> dict[str, Any]:
    data = yaml.safe_load((config_dir / name).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{name} 형식이 올바르지 않습니다")
    return data


@lru_cache
def load_rag_config(config_dir: Path = CONFIG_DIR) -> RagConfig:
    config = RagConfig.model_validate(_load(config_dir))
    for source_key, tau in config.retrieval.thresholds.items():
        if not 0.0 <= tau <= 1.0:
            raise ValueError(f"τ는 0~1이어야 합니다: {source_key}={tau}")
    return config


@lru_cache
def load_llm_config(config_dir: Path = CONFIG_DIR) -> LlmConfig:
    return LlmConfig.model_validate(_load(config_dir, "models.yaml")["llm"])


@lru_cache
def load_rewrite_model_config(config_dir: Path = CONFIG_DIR) -> RewriteModelConfig:
    return RewriteModelConfig.model_validate(_load(config_dir, "models.yaml")["rewrite"])


@lru_cache
def load_compare_model_config(config_dir: Path = CONFIG_DIR) -> CompareModelConfig:
    return CompareModelConfig.model_validate(_load(config_dir, "models.yaml")["compare"])

"""서비스 검색·생성 설정 로더 — `configs/rag.yaml`(ADR-008, 정책서 §5.3)·`models.yaml` `llm`.

τ는 source_key별 값이고 `Settings`의 `TAU_{SOURCE_KEY}` 덮어쓰기가 우선한다.
"""

from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from src.config.ingest_config import CONFIG_DIR

CONTEXT_BUDGET_CAP = 3000  # 정책서 미결정 사항 "컨텍스트 토큰 예산" — 상한 3,000은 고정


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


class RagConfig(BaseModel):
    retrieval: RetrievalConfig


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

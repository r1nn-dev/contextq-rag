"""인덱스 빌드 설정 로더 — `configs/ingest.yaml`, `configs/models.yaml` (비밀값 아님).

청킹 파라미터와 그 해시는 run에 기록되고 chunk_id의 구성 요소다 (정책서 §4.1, INV-04).
"""

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

CONFIG_DIR = Path(__file__).resolve().parents[2] / "configs"

Strategy = Literal["A", "B", "C"]


class ChunkingConfig(BaseModel):
    default_strategy: Strategy
    strategies: dict[Strategy, dict[str, Any]] = Field(min_length=3)

    def params(self, strategy: Strategy) -> dict[str, Any]:
        return dict(self.strategies[strategy])


def params_hash(params: dict[str, Any]) -> str:
    """chunk_params의 SHA-256 앞 8자 — 키 순서·공백에 영향받지 않게 정규화한다."""
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:8]


def _load_yaml(name: str, config_dir: Path) -> dict[str, Any]:
    data = yaml.safe_load((config_dir / name).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{name} 형식이 올바르지 않습니다")
    return data


@lru_cache
def load_chunking_config(config_dir: Path = CONFIG_DIR) -> ChunkingConfig:
    return ChunkingConfig.model_validate(_load_yaml("ingest.yaml", config_dir))


@lru_cache
def embedding_model_name(config_dir: Path = CONFIG_DIR) -> str:
    """청크 메타데이터·run에 기록할 임베딩 모델 이름 (INV-03)."""
    return str(_load_yaml("models.yaml", config_dir)["embedding"]["model"])


class EmbeddingConfig(BaseModel):
    model: str
    dimensions: int = Field(gt=0)
    batch_size: int = Field(gt=0, le=2048)
    timeout_seconds: float = Field(gt=0)
    max_retries: int = Field(ge=0)
    price_per_1m_tokens_usd: float = Field(ge=0)
    # 서비스 질의 임베딩 — 인덱스 빌드(timeout_seconds·max_retries)와 따로 둔다 (정책서 §2.1)
    query_timeout_seconds: float = Field(gt=0)
    query_max_retries: int = Field(ge=0)


@lru_cache
def load_embedding_config(config_dir: Path = CONFIG_DIR) -> EmbeddingConfig:
    return EmbeddingConfig.model_validate(_load_yaml("models.yaml", config_dir)["embedding"])


class SmokeQuestion(BaseModel):
    question: str = Field(min_length=1)
    expected_file: str = Field(min_length=1)


class SmokeConfig(BaseModel):
    """스모크 질문. τ는 서비스와 같은 `configs/rag.yaml` 값을 쓴다 (정책서 §4.4 "top-1 ≥ τ")."""

    top_k: int = Field(gt=0)
    sources: dict[str, list[SmokeQuestion]]


@lru_cache
def load_smoke_config(config_dir: Path = CONFIG_DIR) -> SmokeConfig:
    return SmokeConfig.model_validate(_load_yaml("smoke_questions.yaml", config_dir))

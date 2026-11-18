"""비교 모드 출력 — 정책서 §5.6, rag-pipeline.md §5.2, 계약 `compareResult`.

모델 출력 스키마(Structured Outputs `response_format`)와 `done.compareResult`가 같은 모양이다.
내부 키는 snake_case 그대로다(정책서 §9.3). 후처리 전·후 모두 이 타입을 쓴다.
"""

from pydantic import BaseModel, ConfigDict


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")  # Structured Outputs strict 스키마


class CompareSide(_Strict):
    summary: str
    citations: list[str]  # A측 A1…Ak, B측 B1…Bk
    no_evidence: bool  # τ 미달이면 서버가 true로 고정한다


class CompareChange(_Strict):
    aspect: str
    a: str
    b: str
    citations_a: list[str]
    citations_b: list[str]


class CompareResult(_Strict):
    version_a: CompareSide
    version_b: CompareSide
    changes: list[CompareChange]

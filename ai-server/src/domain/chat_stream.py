"""내부 스트림 요청·SSE 이벤트 — api-spec.md §6.1·부록 B, `contracts/sse-events.schema.json`.

- 요청 필드는 camelCase로 받는다(`requestId`, `sourceKey`, …).
- 이벤트는 계약 스키마 그대로 camelCase dict로 만든다. 값이 없는 선택 필드 중
  스키마가 null을 허용하지 않는 것(`commitSha` 등)은 키를 빼고, null을 허용하는 것은 null로 둔다.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from pydantic.alias_generators import to_camel

from src.domain.retrieval import RetrievedChunk

Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class HistoryMessage(BaseModel):
    """정책서 §5.1 — 최근 3턴(6메시지), 메시지당 2,000자."""

    role: Literal["user", "assistant"]
    content: str = Field(max_length=2000)


class ChatStreamRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    request_id: str | None = Field(default=None, min_length=1, max_length=100)
    mode: Literal["SINGLE", "COMPARE"] = "SINGLE"
    source_key: str | None = Field(default=None, min_length=1, max_length=50)
    source_key_a: str | None = None
    source_key_b: str | None = None
    question: Question
    history: list[HistoryMessage] = Field(default_factory=list, max_length=6)
    prompt_version: str | None = Field(default=None, min_length=1, max_length=50)

    @model_validator(mode="after")
    def _single_mode_only(self) -> "ChatStreamRequest":
        if self.mode == "COMPARE":
            raise ValueError("비교 모드(COMPARE)는 아직 지원하지 않습니다")
        if not self.source_key:
            raise ValueError("SINGLE 모드에는 sourceKey가 필요합니다")
        return self


# --- SSE 이벤트 (upstream 구간: ai-server → backend) -----------------------------


def source_payload(rank: int, chunk: RetrievedChunk) -> dict[str, Any]:
    """meta.sources 항목. rank = 컨텍스트 순서 = 인용 번호 (INV-08)."""
    return {
        "rank": rank,
        "headingPath": chunk["heading_path"],
        "permalink": chunk["permalink"],
        "siteUrl": chunk["site_url"],
        "similarity": round(chunk["similarity"], 4),
    }


@dataclass(frozen=True)
class MetaEvent:
    request_id: str
    source_key: str
    ingest_run_id: int
    commit_sha: str | None
    ingested_at: date | None
    no_context: bool
    sources: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "event": "meta",
            "requestId": self.request_id,
            "sourceKey": self.source_key,
            "ingestRunId": self.ingest_run_id,
            "rewrittenQuery": None,  # 질의 재작성(R-7-2) 전
            "noContext": self.no_context,
            "sources": [] if self.no_context else self.sources,
        }
        if self.commit_sha:
            data["commitSha"] = self.commit_sha
        if self.ingested_at:
            data["ingestedAt"] = self.ingested_at.isoformat()
        return data


def token_event(text: str) -> dict[str, Any]:
    return {"event": "token", "t": text}


@dataclass
class Latency:
    rewrite_ms: int | None = None  # 재작성 없음(SKIPPED) → null
    embed_ms: int | None = None
    retrieve_ms: int | None = None
    ttft_ms: int | None = None
    total_ms: int | None = None

    def to_dict(self) -> dict[str, int | None]:
        return {
            "rewriteMs": self.rewrite_ms,
            "embedMs": self.embed_ms,
            "retrieveMs": self.retrieve_ms,
            "ttftMs": self.ttft_ms,
            "totalMs": self.total_ms,
        }


@dataclass(frozen=True)
class DoneEvent:
    status: Literal["COMPLETED", "PARTIAL", "NO_CONTEXT", "FAILED"]
    latency: Latency
    status_reason: str | None = None
    finish_reason: str | None = None
    usage: dict[str, int] | None = None
    invalid_citations: list[int] = field(default_factory=list)
    model: str | None = None
    prompt_version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event": "done",
            "status": self.status,
            "statusReason": self.status_reason,
            "finishReason": self.finish_reason,
            "usage": self.usage,
            "latency": self.latency.to_dict(),
            "invalidCitations": self.invalid_citations,
            "model": self.model,
            "promptVersion": self.prompt_version,
        }


def error_event(code: str, message: str, request_id: str, *, partial: bool) -> dict[str, Any]:
    """200 이후 오류 (INV-09). partial = token을 1개 이상 보냈는지."""
    return {
        "event": "error",
        "code": code,
        "message": message,
        "requestId": request_id,
        "partial": partial,
    }

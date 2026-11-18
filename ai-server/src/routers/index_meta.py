"""내부 소스 조회·포인터 reload·인덱스 현황 — api-spec.md §6.3·§6.5·§6.6, 정책서 §4.5·§9.4, ADR-012.

- `GET /internal/v1/sources`: backend가 ai 스키마를 읽지 않고 소스·ACTIVE run을 얻는 유일한 경로.
  backend가 60초 캐시하므로 여기서는 캐시하지 않는다.
- `POST /internal/v1/index/reload`: 포인터 캐시를 비우고 다시 읽는다 → 다음 질의부터 새 run.
- `GET /internal/v1/index/status`: 관리자 대시보드용 ACTIVE run 상세와 최근 수집 이력(캐시 없음).
"""

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.ingest_status import IngestStatus
from src.domain.tables import ComparePair, IngestRun, Source
from src.retrieval.pointers import find_active_run, ingested_on
from src.routers.auth import verify_internal_token
from src.routers.services import IndexServices, get_index_services

router = APIRouter(
    prefix="/internal/v1", tags=["internal"], dependencies=[Depends(verify_internal_token)]
)


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SourceItem(_Camel):
    source_key: str
    framework: str
    version_label: str
    display_name: str
    enabled: bool
    active_run_id: int | None
    commit_sha: str | None
    ingested_at: date | None
    chunk_count: int | None


class ComparePairItem(_Camel):
    source_key_a: str
    source_key_b: str


class SourcesResponse(_Camel):
    sources: list[SourceItem]
    compare_pairs: list[ComparePairItem]


def list_sources(session: Session) -> SourcesResponse:
    items = []
    for source in session.scalars(select(Source).order_by(Source.id)):
        run = find_active_run(session, source.source_key)
        items.append(
            SourceItem(
                source_key=source.source_key,
                framework=source.framework,
                version_label=source.version_label,
                display_name=source.display_name,
                enabled=source.enabled,
                active_run_id=run.id if run else None,
                commit_sha=run.commit_sha if run else None,
                ingested_at=ingested_on(run) if run else None,
                chunk_count=run.chunk_count if run else None,
            )
        )
    pairs = [
        ComparePairItem(source_key_a=pair.source_key_a, source_key_b=pair.source_key_b)
        for pair in session.scalars(select(ComparePair).order_by(ComparePair.id))
    ]
    return SourcesResponse(sources=items, compare_pairs=pairs)


@router.get("/sources", response_model=SourcesResponse, response_model_by_alias=True)
async def sources(
    index: Annotated[IndexServices, Depends(get_index_services)],
) -> SourcesResponse:
    def query() -> SourcesResponse:
        with index.session_factory() as session:
            return list_sources(session)

    return await asyncio.to_thread(query)


class ReloadRequest(_Camel):
    source_key: str = Field(min_length=1, max_length=50)


class ReloadResponse(_Camel):
    source_key: str
    active_run_id: int
    reloaded_at: str  # UTC ISO-8601


@router.post("/index/reload", response_model=ReloadResponse, response_model_by_alias=True)
async def reload_index(
    body: ReloadRequest,
    index: Annotated[IndexServices, Depends(get_index_services)],
) -> ReloadResponse:
    """포인터 캐시를 비우고 다시 읽는다. 없는 소스 404 · 비활성 409 · ACTIVE 없음 503."""
    index.pointers.invalidate(body.source_key)
    active = await asyncio.to_thread(index.pointers.get, body.source_key)
    reloaded_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    return ReloadResponse(
        source_key=body.source_key, active_run_id=active.run_id, reloaded_at=reloaded_at
    )


# --- 인덱스 현황 (§6.6) -----------------------------------------------------------------

RECENT_RUNS = 5  # api-spec §6.6 소스별 최근 수집 run 수


def _utc(value: datetime | None) -> str | None:
    """UTC ISO-8601(`Z`). 시간대가 없는 값은 UTC로 본다(SQLite 테스트)."""
    if value is None:
        return None
    aware = value if value.tzinfo else value.replace(tzinfo=UTC)
    return aware.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class ActiveRunItem(_Camel):
    ingest_run_id: int
    status: str
    commit_sha: str | None
    chunk_strategy: str | None
    chunk_count: int | None
    prev_chunk_count: int | None
    embedding_model: str | None
    embedding_tokens: int | None
    embedding_cost_usd: float | None
    ingest_duration_ms: int | None
    started_at: str | None
    completed_at: str | None


class RecentRunItem(_Camel):
    ingest_run_id: int
    status: str
    started_at: str | None
    failure_stage: str | None = Field(default=None, exclude_if=lambda v: v is None)  # FAILED만


class IndexStatusItem(_Camel):
    source_key: str
    display_name: str
    enabled: bool
    active_run: ActiveRunItem | None
    recent_runs: list[RecentRunItem]


class IndexStatusResponse(_Camel):
    sources: list[IndexStatusItem]


def _cost(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def index_status(session: Session) -> IndexStatusResponse:
    items = []
    for source in session.scalars(select(Source).order_by(Source.id)):
        run = find_active_run(session, source.source_key)
        active = (
            ActiveRunItem(
                ingest_run_id=run.id,
                status=run.status,
                commit_sha=run.commit_sha,
                chunk_strategy=run.chunk_strategy,
                chunk_count=run.chunk_count,
                prev_chunk_count=run.prev_chunk_count,
                embedding_model=run.embedding_model,
                embedding_tokens=run.embedding_tokens,
                embedding_cost_usd=_cost(run.embedding_cost_usd),
                ingest_duration_ms=run.ingest_duration_ms,
                started_at=_utc(run.started_at),
                completed_at=_utc(run.completed_at),
            )
            if run
            else None
        )
        recent = session.scalars(
            select(IngestRun)
            .where(IngestRun.source_key == source.source_key)
            .order_by(IngestRun.created_at.desc(), IngestRun.id.desc())
            .limit(RECENT_RUNS)
        )
        runs = [
            RecentRunItem(
                ingest_run_id=r.id,
                status=r.status,
                started_at=_utc(r.started_at),
                failure_stage=r.failure_stage if r.status == IngestStatus.FAILED else None,
            )
            for r in recent
        ]
        items.append(
            IndexStatusItem(
                source_key=source.source_key,
                display_name=source.display_name,
                enabled=source.enabled,
                active_run=active,
                recent_runs=runs,
            )
        )
    return IndexStatusResponse(sources=items)


@router.get("/index/status", response_model=IndexStatusResponse, response_model_by_alias=True)
async def status(
    index: Annotated[IndexServices, Depends(get_index_services)],
) -> IndexStatusResponse:
    def query() -> IndexStatusResponse:
        with index.session_factory() as session:
            return index_status(session)

    return await asyncio.to_thread(query)

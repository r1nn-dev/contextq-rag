"""내부 소스 조회·포인터 reload — api-spec.md §6.3·§6.5, 정책서 §4.5·§9.4, ADR-012.

- `GET /internal/v1/sources`: backend가 ai 스키마를 읽지 않고 소스·ACTIVE run을 얻는 유일한 경로.
  backend가 60초 캐시하므로 여기서는 캐시하지 않는다.
- `POST /internal/v1/index/reload`: 포인터 캐시를 비우고 다시 읽는다 → 다음 질의부터 새 run.
"""

import asyncio
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.tables import ComparePair, Source
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

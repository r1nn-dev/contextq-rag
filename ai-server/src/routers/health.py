"""`GET /internal/v1/health` — Chroma·DB·소스별 ACTIVE run (api-spec.md §6.2, 정책서 §9.4).

- 판정 대상은 활성(`enabled`) 소스. ACTIVE = 포인터 → ACTIVE run 그리고 그 컬렉션 존재.
- 하나라도 ACTIVE가 아니거나 Chroma·DB를 쓸 수 없으면 503 `degraded`.
- Compose healthcheck가 헤더 없이 부르므로 토큰을 요구하지 않고, OpenAI 키도 쓰지 않는다.
- 헬스는 실제 상태를 보여야 하므로 포인터 캐시가 아니라 DB를 직접 읽는다.
"""

import asyncio
import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy import select

from src.domain.tables import Source
from src.retrieval.errors import RetrievalError
from src.retrieval.pointers import load_active_index
from src.routers.services import IndexServices, get_index_services

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/v1", tags=["internal"])

_PROBE_COLLECTION = "__health_probe__"  # 존재 여부만 묻는다 (만들지 않음)


class SourceHealth(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    active_run: bool
    ingest_run_id: int | None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    chroma: Literal["loaded", "error"]
    database: Literal["ok", "error"]
    sources: dict[str, SourceHealth]


def check_health(index: IndexServices | None) -> HealthResponse:
    if index is None:
        return HealthResponse(status="degraded", chroma="error", database="error", sources={})
    try:
        index.store.has_collection(_PROBE_COLLECTION)
        chroma: Literal["loaded", "error"] = "loaded"
    except Exception:
        logger.exception("health_chroma_failed")
        chroma = "error"
    sources: dict[str, SourceHealth] = {}
    try:
        with index.session_factory() as session:
            keys = session.scalars(select(Source.source_key).where(Source.enabled.is_(True))).all()
            for key in keys:
                try:
                    active = load_active_index(session, key)
                except RetrievalError:
                    sources[key] = SourceHealth(active_run=False, ingest_run_id=None)
                    continue
                exists = chroma == "loaded" and index.store.has_collection(active.collection)
                sources[key] = SourceHealth(
                    active_run=exists, ingest_run_id=active.run_id if exists else None
                )
        database: Literal["ok", "error"] = "ok"
    except Exception:
        logger.exception("health_database_failed")
        database, sources = "error", {}
    healthy = (
        chroma == "loaded" and database == "ok" and all(s.active_run for s in sources.values())
    )
    return HealthResponse(
        status="ok" if healthy else "degraded", chroma=chroma, database=database, sources=sources
    )


def _index_or_none(request: Request) -> IndexServices | None:
    """만들지 못하면 None → degraded. 앱 상태에 이미 있으면 그것을 쓴다(테스트 주입 포함)."""
    if hasattr(request.app.state, "index_services"):
        cached: IndexServices | None = request.app.state.index_services
        return cached
    try:
        return get_index_services(request)
    except Exception:
        logger.exception("health_index_services_failed")
        return None


@router.get("/health", response_model=HealthResponse)
async def health(
    index: Annotated[IndexServices | None, Depends(_index_or_none)],
) -> JSONResponse:
    """200 = 모든 활성 소스 ACTIVE, 503 = degraded."""
    result = await asyncio.to_thread(check_health, index)
    return JSONResponse(
        status_code=200 if result.status == "ok" else 503,
        content=result.model_dump(by_alias=True),
    )

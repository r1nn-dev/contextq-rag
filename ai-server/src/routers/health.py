from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/internal/v1", tags=["internal"])


class HealthResponse(BaseModel):
    """API 명세 §6 내부 헬스체크 응답.

    골격 단계에서는 프로세스 기동 여부만 반환한다.
    Chroma 로드(`chroma`)와 소스별 ACTIVE run(`sources`) 검사는 R-4-5에서 추가한다.
    """

    status: Literal["ok", "degraded"]


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Docker Compose healthcheck가 호출하는 내부망 전용 엔드포인트."""
    return HealthResponse(status="ok")

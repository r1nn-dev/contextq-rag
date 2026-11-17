"""내부 API 인증 — ADR-012 `X-Internal-Token` (api-spec.md §6).

- 토큰은 상수 시간으로 비교한다.
- 서버에 `INTERNAL_TOKEN`이 없으면 모든 요청을 거부한다(fail closed).
- `GET /internal/v1/health`는 이 의존성을 쓰지 않는다 (Compose healthcheck).
"""

import hmac
from typing import Annotated

from fastapi import Header, Request

from src.config.settings import Settings
from src.routers.errors import ApiError


def app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


async def verify_internal_token(
    request: Request,
    x_internal_token: Annotated[str | None, Header(alias="X-Internal-Token")] = None,
) -> None:
    expected = app_settings(request).internal_token
    supplied = x_internal_token or ""
    if not expected or not hmac.compare_digest(supplied.encode(), expected.encode()):
        raise ApiError(401, "INTERNAL_UNAUTHORIZED", "내부 API 인증에 실패했습니다")

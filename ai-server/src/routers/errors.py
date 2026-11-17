"""내부 API 스트림 전 오류 응답 — api-spec.md §6.1, 정책서 §9.2.

본문: `{"code", "message", "request_id", "timestamp"}`. 스트림이 시작된 뒤의 오류는
HTTP 상태가 아니라 SSE `error` 이벤트로만 보낸다(INV-09) — 이 모듈은 200 이전만 다룬다.
"""

import uuid
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.pipeline.prompts import PromptNotFoundError
from src.retrieval.errors import RetrievalError


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def request_id_of(request: Request) -> str:
    """정책서 §9.4 — 전파된 `X-Request-Id`, 없으면 새 UUID v4."""
    return request.headers.get("X-Request-Id") or str(uuid.uuid4())


def error_response(status: int, code: str, message: str, request_id: str) -> JSONResponse:
    timestamp = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    return JSONResponse(
        status_code=status,
        content={
            "code": code,
            "message": message,
            "request_id": request_id,
            "timestamp": timestamp,
        },
    )


def _validation_message(exc: RequestValidationError) -> str:
    first = exc.errors()[0] if exc.errors() else {}
    location = ".".join(str(part) for part in first.get("loc", ()) if part != "body")
    reason = str(first.get("msg", "입력 형식이 올바르지 않습니다"))
    return f"요청 검증 실패: {location} — {reason}" if location else f"요청 검증 실패: {reason}"


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        return error_response(exc.status, exc.code, exc.message, request_id_of(request))

    @app.exception_handler(RequestValidationError)
    async def _invalid(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(
            400, "INVALID_REQUEST", _validation_message(exc), request_id_of(request)
        )

    @app.exception_handler(PromptNotFoundError)
    async def _prompt(request: Request, exc: PromptNotFoundError) -> JSONResponse:
        return error_response(400, "INVALID_REQUEST", str(exc), request_id_of(request))

    @app.exception_handler(RetrievalError)
    async def _retrieval(request: Request, exc: RetrievalError) -> JSONResponse:
        return error_response(exc.http_status, exc.code, str(exc), request_id_of(request))

from fastapi import FastAPI

from src.config.settings import Settings, settings
from src.routers import chat_stream, health, index_meta
from src.routers.errors import install_error_handlers


def create_app(app_settings: Settings) -> FastAPI:
    """FastAPI 앱을 생성한다.

    prod 프로필에서는 /docs·/redoc·/openapi.json을 노출하지 않는다 (정책서 §9.1).
    """
    docs_enabled = app_settings.docs_enabled
    app = FastAPI(
        title="ContextQ RAG Server",
        description="공식 기술 문서 연계 RAG Q&A API",
        version="0.1.0",
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    app.state.settings = app_settings
    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(chat_stream.router)
    app.include_router(index_meta.router)
    return app


# uvicorn 엔트리포인트 (src.main:app) — 워커 수는 Dockerfile에서 1로 고정
app = create_app(settings)

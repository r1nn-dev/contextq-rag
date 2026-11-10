from fastapi import FastAPI

# FastAPI 앱 인스턴스 생성
# title, description, version은 /docs Swagger UI에 표시됨
app = FastAPI(
    title="ContextQ RAG Server",
    description="공식 기술 문서 연계 RAG Q&A API",
    version="0.1.0",
)


@app.get("/health")
async def health() -> dict[str, str]:
    """헬스 체크 엔드포인트.

    Docker Compose healthcheck, Kubernetes liveness probe가 이 경로를 호출.
    """
    return {"status": "ok"}

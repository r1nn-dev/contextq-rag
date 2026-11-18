FROM python:3.12-slim AS builder

WORKDIR /app

# uv 버전을 로컬 개발 버전과 같게 고정한다 (latest는 빌드마다 바뀔 수 있음)
COPY --from=ghcr.io/astral-sh/uv:0.11.1 /uv /uvx /bin/

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev  # excludes ruff, mypy, pytest

FROM python:3.12-slim AS runtime

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY src/ src/
COPY configs/ configs/
# ai 스키마 마이그레이션 — 기동할 때 적용한다 (아래 CMD)
COPY alembic.ini ./
COPY alembic/ alembic/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

# ai 스키마는 ai-server가 소유한다(정책서 §9.4). 마이그레이션이 실패하면 서버를 띄우지 않는다.
# --workers 1: 임베디드 Chroma는 단일 프로세스 접근만 허용한다 (ADR-002)
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 1"]

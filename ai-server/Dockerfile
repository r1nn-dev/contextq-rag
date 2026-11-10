FROM python:3.12-slim AS builder

WORKDIR /app

# copy uv binary from official image (faster than pip install uv)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev  # excludes ruff, mypy, pytest

FROM python:3.12-slim AS runtime

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY src/ src/
COPY configs/ configs/

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# --workers 1: single worker for MVP; scale via Docker Compose in production
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
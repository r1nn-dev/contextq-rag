"""통합 테스트 공용 픽스처 — 실제 PostgreSQL이 필요하다.

`TEST_DATABASE_URL`(예: `postgresql+psycopg://user:pw@localhost:55432/db`)이 없으면 건너뛴다.
테스트는 `ai` 스키마를 만들고 지우므로 개발용 DB가 아닌 임시 DB를 가리켜야 한다.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text

from alembic import command

AI_SERVER_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def pg_engine() -> Iterator[Engine]:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL이 없어 PostgreSQL 통합 테스트를 건너뜁니다")
    engine = create_engine(url)
    yield engine
    engine.dispose()


def alembic_run(engine: Engine, action: str, revision: str | None = None) -> None:
    """주어진 엔진 커넥션으로 alembic upgrade/downgrade/check를 실행한다."""
    cfg = Config(str(AI_SERVER_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(AI_SERVER_ROOT / "alembic"))
    cfg.attributes["configure_logger"] = False
    with engine.connect() as connection:
        cfg.attributes["connection"] = connection
        if revision is None:
            getattr(command, action)(cfg)
        else:
            getattr(command, action)(cfg, revision)
        connection.commit()


@pytest.fixture()
def migrated(pg_engine: Engine) -> Iterator[Engine]:
    """빈 상태에서 head까지 올린 DB를 주고, 끝나면 ai 스키마를 지운다."""
    with pg_engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS ai CASCADE"))
    alembic_run(pg_engine, "upgrade", "head")
    yield pg_engine
    with pg_engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS ai CASCADE"))

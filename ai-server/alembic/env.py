"""Alembic 환경 — ai 스키마 전용 마이그레이션.

- `app` 스키마는 backend Flyway, `ai` 스키마는 ai-server Alembic이 소유한다 (db-design §1.2).
- 접속 정보는 alembic.ini가 아니라 `src.config.settings`(환경 변수)에서 읽는다.
"""

from logging.config import fileConfig

from sqlalchemy import create_engine, pool, text

from alembic import context
from src.config.settings import settings

AI_SCHEMA = "ai"

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ai 스키마 모델의 MetaData — 테이블을 추가하는 이슈(R-2-1)에서 연결한다
target_metadata = None


def run_migrations_offline() -> None:
    """DB 연결 없이 SQL 스크립트만 출력한다."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema=AI_SCHEMA,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """ai 스키마를 보장한 뒤 search_path=ai 커넥션으로 마이그레이션을 실행한다."""
    connectable = create_engine(
        settings.database_url,
        poolclass=pool.NullPool,
        connect_args={"options": f"-c search_path={AI_SCHEMA}"},
    )

    with connectable.connect() as connection:
        # 버전 테이블을 ai 스키마에 두려면 스키마가 먼저 있어야 한다
        connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {AI_SCHEMA}"))
        connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema=AI_SCHEMA,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

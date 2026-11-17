"""Alembic 환경 — ai 스키마 전용 마이그레이션.

- `app` 스키마는 backend Flyway, `ai` 스키마는 ai-server Alembic이 소유한다 (db-design §1.2).
- 접속 정보는 alembic.ini가 아니라 `src.config.settings`(환경 변수)에서 읽는다.
- 호출자가 `config.attributes["connection"]`으로 커넥션을 넘기면 그 커넥션을 쓴다 (통합 테스트).
"""

from logging.config import fileConfig

from sqlalchemy import Connection, create_engine, pool, text

from alembic import context
from src.config.settings import settings
from src.domain.tables import AI_SCHEMA, Base

config = context.config

if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


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


def _include_name(name: str | None, type_: str, parent_names: object) -> bool:
    """autogenerate 비교 대상을 ai 스키마로 한정한다 (app 스키마는 Flyway 소유)."""
    if type_ == "schema":
        return name == AI_SCHEMA
    return name != "alembic_version"


def _run_with(connection: Connection) -> None:
    # 버전 테이블을 ai 스키마에 두려면 스키마가 먼저 있어야 한다
    connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {AI_SCHEMA}"))
    connection.commit()

    # 리비전은 schema="ai"를 명시하므로 search_path를 바꾸지 않는다.
    # (search_path=ai면 반영 테이블이 스키마 없이 보여 autogenerate 비교가 어긋난다)
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table_schema=AI_SCHEMA,
        include_schemas=True,
        include_name=_include_name,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """ai 스키마를 보장한 뒤 마이그레이션을 실행한다."""
    provided = config.attributes.get("connection")
    if provided is not None:
        _run_with(provided)
        return

    connectable = create_engine(settings.database_url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        _run_with(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

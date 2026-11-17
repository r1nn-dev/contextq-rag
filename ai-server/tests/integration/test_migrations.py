"""ai 스키마 마이그레이션 up·down과 제약 검증 (실제 PostgreSQL)."""

import pytest
from sqlalchemy import Engine, inspect

from tests.integration.conftest import alembic_run

pytestmark = pytest.mark.integration

TABLES = {"sources", "compare_pairs", "ingest_runs", "index_pointers"}


def _ai_tables(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names(schema="ai")) - {"alembic_version"}


def test_upgrade_creates_tables_and_downgrade_removes_them(migrated: Engine) -> None:
    assert _ai_tables(migrated) == TABLES

    alembic_run(migrated, "downgrade", "base")
    assert _ai_tables(migrated) == set()

    alembic_run(migrated, "upgrade", "head")
    assert _ai_tables(migrated) == TABLES


def test_models_match_migrations(migrated: Engine) -> None:
    # SQLAlchemy 모델과 리비전 결과가 다르면 alembic check가 예외를 낸다
    alembic_run(migrated, "check")

"""소스 카탈로그·비교 쌍 시드 — 정책서 §3.1·§3.2

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "ai"

sources = sa.table(
    "sources",
    sa.column("source_key", sa.String),
    sa.column("framework", sa.String),
    sa.column("version_label", sa.String),
    sa.column("display_name", sa.String),
    sa.column("repo_url", sa.String),
    sa.column("ref", sa.String),
    sa.column("doc_path", sa.String),
    sa.column("doc_format", sa.String),
    sa.column("adapter_class", sa.String),
    sa.column("enabled", sa.Boolean),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("updated_at", sa.DateTime(timezone=True)),
    schema=SCHEMA,
)
compare_pairs = sa.table(
    "compare_pairs",
    sa.column("source_key_a", sa.String),
    sa.column("source_key_b", sa.String),
    sa.column("created_at", sa.DateTime(timezone=True)),
    schema=SCHEMA,
)

SOURCE_ROWS = [
    {
        "source_key": "langchain_v03",
        "framework": "langchain",
        "version_label": "v0.3",
        "display_name": "LangChain v0.3",
        "repo_url": "langchain-ai/langchain",
        "ref": "v0.3",
        "doc_path": "docs/docs/",
        "doc_format": "DOCUSAURUS",
        "adapter_class": "DocusaurusAdapter",
    },
    {
        "source_key": "langchain_v1x",
        "framework": "langchain",
        "version_label": "v1.x",
        "display_name": "LangChain v1.x",
        "repo_url": "langchain-ai/docs",
        "ref": "main",
        "doc_path": "src/oss/",
        "doc_format": "MINTLIFY",
        "adapter_class": "MintlifyAdapter",
    },
]


def upgrade() -> None:
    # 기본값은 DB DEFAULT가 아니라 INSERT 값으로 넣는다 (db-design §4)
    now = sa.func.now()
    for row in SOURCE_ROWS:
        op.execute(sa.insert(sources).values(**row, enabled=True, created_at=now, updated_at=now))
    # 순서는 항상 구버전 = A, 신버전 = B (정책서 §3.2)
    op.execute(
        sa.insert(compare_pairs).values(
            source_key_a="langchain_v03", source_key_b="langchain_v1x", created_at=now
        )
    )


def downgrade() -> None:
    op.execute(
        sa.delete(compare_pairs).where(
            compare_pairs.c.source_key_a == "langchain_v03",
            compare_pairs.c.source_key_b == "langchain_v1x",
        )
    )
    keys = [row["source_key"] for row in SOURCE_ROWS]
    op.execute(sa.delete(sources).where(sources.c.source_key.in_(keys)))

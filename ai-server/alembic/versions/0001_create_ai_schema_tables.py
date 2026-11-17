"""ai 스키마 테이블 생성 — sources · compare_pairs · ingest_runs · index_pointers

db-design §3.9~3.12. DB DEFAULT·ON DELETE CASCADE 미사용 (§4).

Revision ID: 0001
Revises:
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "ai"


def _timestamps(*, with_updated: bool = True) -> list[sa.Column]:
    columns = [sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)]
    if with_updated:
        columns.append(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    return columns


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("source_key", sa.String(50), nullable=False),
        sa.Column("framework", sa.String(50), nullable=False),
        sa.Column("version_label", sa.String(20), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("repo_url", sa.String(200), nullable=False),
        sa.Column("ref", sa.String(50), nullable=False),
        sa.Column("doc_path", sa.String(200), nullable=False),
        sa.Column("doc_format", sa.String(30), nullable=False),
        sa.Column("adapter_class", sa.String(100), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_sources"),
        sa.UniqueConstraint("source_key", name="uq_sources_key"),
        sa.UniqueConstraint("framework", "version_label", name="uq_sources_fw_ver"),
        schema=SCHEMA,
    )
    op.create_table(
        "compare_pairs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("source_key_a", sa.String(50), nullable=False),
        sa.Column("source_key_b", sa.String(50), nullable=False),
        *_timestamps(with_updated=False),
        sa.PrimaryKeyConstraint("id", name="pk_compare_pairs"),
        sa.UniqueConstraint("source_key_a", "source_key_b", name="uq_cp_pair"),
        sa.ForeignKeyConstraint(
            ["source_key_a"], [f"{SCHEMA}.sources.source_key"], name="fk_cp_source_a"
        ),
        sa.ForeignKeyConstraint(
            ["source_key_b"], [f"{SCHEMA}.sources.source_key"], name="fk_cp_source_b"
        ),
        schema=SCHEMA,
    )
    op.create_table(
        "ingest_runs",
        # 스냅샷 복원 시 run id를 명시해 INSERT하므로 BY DEFAULT (db-design §3.11)
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("source_key", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("commit_sha", sa.CHAR(40), nullable=True),
        sa.Column("chunk_strategy", sa.String(10), nullable=True),
        sa.Column("chunk_params", postgresql.JSONB(), nullable=True),
        sa.Column("chunk_params_hash", sa.String(8), nullable=True),
        sa.Column("embedding_model", sa.String(100), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=True),
        sa.Column("prev_chunk_count", sa.Integer(), nullable=True),
        sa.Column("missing_snippets_count", sa.Integer(), nullable=True),
        sa.Column("accept_drift", sa.Boolean(), nullable=False),
        sa.Column("failure_stage", sa.String(30), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("validation_report", postgresql.JSONB(), nullable=True),
        sa.Column("embedding_tokens", sa.Integer(), nullable=True),
        sa.Column("embedding_cost_usd", sa.Numeric(8, 6), nullable=True),
        sa.Column("ingest_duration_ms", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_ingest_runs"),
        schema=SCHEMA,
    )
    op.create_index("idx_ir_source_status", "ingest_runs", ["source_key", "status"], schema=SCHEMA)
    op.create_index(
        "idx_ir_source_created",
        "ingest_runs",
        ["source_key", sa.text("created_at DESC")],
        schema=SCHEMA,
    )
    op.create_table(
        "index_pointers",
        sa.Column("source_key", sa.String(50), nullable=False),
        sa.Column("active_run_id", sa.BigInteger(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("source_key", name="pk_index_pointers"),
        sa.ForeignKeyConstraint(["active_run_id"], [f"{SCHEMA}.ingest_runs.id"], name="fk_ip_run"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("index_pointers", schema=SCHEMA)
    op.drop_index("idx_ir_source_created", table_name="ingest_runs", schema=SCHEMA)
    op.drop_index("idx_ir_source_status", table_name="ingest_runs", schema=SCHEMA)
    op.drop_table("ingest_runs", schema=SCHEMA)
    op.drop_table("compare_pairs", schema=SCHEMA)
    op.drop_table("sources", schema=SCHEMA)

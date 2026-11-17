"""ai 스키마 테이블 정의 — db-design §3.9~3.12.

- 기본값은 DB `DEFAULT`가 아니라 애플리케이션(INSERT 시점)에서 넣는다 (db-design §4).
- `ON DELETE CASCADE`는 쓰지 않는다. FK는 ai 스키마 내부에서만 건다.
- `ingest_runs.source_key`는 FK 없이 값만 저장한다 (운영 유연성, db-design §3.11).
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CHAR,
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

AI_SCHEMA = "ai"

# PostgreSQL에서는 JSONB, 단위 테스트용 SQLite에서는 JSON으로 매핑한다
JsonColumn = JSON().with_variant(JSONB(), "postgresql")
# SQLite는 INTEGER PRIMARY KEY만 자동 증가하므로 단위 테스트에서만 INTEGER로 매핑한다
IdColumn = BigInteger().with_variant(Integer(), "sqlite")
Timestamp = DateTime(timezone=True)


class Base(DeclarativeBase):
    # PK 이름을 db-design 표기(pk_<table>)와 맞춘다
    metadata = MetaData(schema=AI_SCHEMA, naming_convention={"pk": "pk_%(table_name)s"})


class Source(Base):
    """소스 카탈로그 — 버전 목록의 유일한 원본 (정책서 §3)."""

    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint("source_key", name="uq_sources_key"),
        UniqueConstraint("framework", "version_label", name="uq_sources_fw_ver"),
    )

    id: Mapped[int] = mapped_column(IdColumn, Identity(always=True), primary_key=True)
    source_key: Mapped[str] = mapped_column(String(50), nullable=False)
    framework: Mapped[str] = mapped_column(String(50), nullable=False)
    version_label: Mapped[str] = mapped_column(String(20), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    repo_url: Mapped[str] = mapped_column(String(200), nullable=False)
    ref: Mapped[str] = mapped_column(String(50), nullable=False)
    doc_path: Mapped[str] = mapped_column(String(200), nullable=False)
    doc_format: Mapped[str] = mapped_column(String(30), nullable=False)
    adapter_class: Mapped[str] = mapped_column(String(100), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(Timestamp, nullable=False, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        Timestamp, nullable=False, default=func.now(), onupdate=func.now()
    )


class ComparePair(Base):
    """비교 쌍 [IMMUTABLE] — 순서는 항상 구버전 = A, 신버전 = B."""

    __tablename__ = "compare_pairs"
    __table_args__ = (UniqueConstraint("source_key_a", "source_key_b", name="uq_cp_pair"),)

    id: Mapped[int] = mapped_column(IdColumn, Identity(always=True), primary_key=True)
    source_key_a: Mapped[str] = mapped_column(
        String(50),
        ForeignKey(f"{AI_SCHEMA}.sources.source_key", name="fk_cp_source_a"),
        nullable=False,
    )
    source_key_b: Mapped[str] = mapped_column(
        String(50),
        ForeignKey(f"{AI_SCHEMA}.sources.source_key", name="fk_cp_source_b"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(Timestamp, nullable=False, default=func.now())


class IngestRun(Base):
    """수집 실행 이력 — 상태 전이는 정책서 §10.1."""

    __tablename__ = "ingest_runs"
    __table_args__ = (Index("idx_ir_source_status", "source_key", "status"),)

    # 스냅샷 복원 시 run id를 그대로 넣어야 하므로 BY DEFAULT (db-design §3.11)
    id: Mapped[int] = mapped_column(IdColumn, Identity(always=False), primary_key=True)
    source_key: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    commit_sha: Mapped[str | None] = mapped_column(CHAR(40))
    chunk_strategy: Mapped[str | None] = mapped_column(String(10))
    chunk_params: Mapped[dict[str, Any] | None] = mapped_column(JsonColumn)
    chunk_params_hash: Mapped[str | None] = mapped_column(String(8))
    embedding_model: Mapped[str | None] = mapped_column(String(100))
    chunk_count: Mapped[int | None] = mapped_column(Integer)
    prev_chunk_count: Mapped[int | None] = mapped_column(Integer)
    missing_snippets_count: Mapped[int | None] = mapped_column(Integer)
    accept_drift: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    failure_stage: Mapped[str | None] = mapped_column(String(30))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    validation_report: Mapped[dict[str, Any] | None] = mapped_column(JsonColumn)
    embedding_tokens: Mapped[int | None] = mapped_column(Integer)
    embedding_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    ingest_duration_ms: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime | None] = mapped_column(Timestamp)
    completed_at: Mapped[datetime | None] = mapped_column(Timestamp)
    created_at: Mapped[datetime] = mapped_column(Timestamp, nullable=False, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        Timestamp, nullable=False, default=func.now(), onupdate=func.now()
    )


# 관리자 수집 이력 목록(최신순) 조회용
Index("idx_ir_source_created", IngestRun.source_key, IngestRun.created_at.desc())


class IndexPointer(Base):
    """소스별 활성 run 포인터 — 소스당 정확히 1행 (INV-01)."""

    __tablename__ = "index_pointers"

    source_key: Mapped[str] = mapped_column(String(50), primary_key=True)
    active_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{AI_SCHEMA}.ingest_runs.id", name="fk_ip_run"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(Timestamp, nullable=False, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        Timestamp, nullable=False, default=func.now(), onupdate=func.now()
    )

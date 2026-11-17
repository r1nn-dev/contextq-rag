"""단위 테스트 공용 픽스처 — DB가 필요한 저장 계층은 인메모리 SQLite로 대신한다."""

import hashlib
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.domain.tables import AI_SCHEMA, Base, Source

CATALOG = [
    ("langchain_v03", "v0.3", "langchain-ai/langchain", "v0.3", "docs/docs/",
     "DOCUSAURUS", "DocusaurusAdapter"),
    ("langchain_v1x", "v1.x", "langchain-ai/docs", "main", "src/oss/",
     "MINTLIFY", "MintlifyAdapter"),
]  # fmt: skip


@pytest.fixture()
def session_factory() -> Iterator[sessionmaker[Session]]:
    """ai 스키마 테이블과 카탈로그 2행이 있는 SQLite 세션 팩토리 (세션 간 같은 DB 공유)."""
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    ).execution_options(schema_translate_map={AI_SCHEMA: None})
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    with factory() as db:
        for key, version, repo, ref, path, fmt, adapter in CATALOG:
            db.add(
                Source(
                    source_key=key,
                    framework="langchain",
                    version_label=version,
                    display_name=f"LangChain {version}",
                    repo_url=repo,
                    ref=ref,
                    doc_path=path,
                    doc_format=fmt,
                    adapter_class=adapter,
                    enabled=True,
                )
            )
        db.commit()
    yield factory
    engine.dispose()


@pytest.fixture()
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as db:
        yield db


class FakeEmbedder:
    """텍스트 해시로 만든 결정적 벡터 — OpenAI 호출 없이 파이프라인을 검증한다."""

    def __init__(self, model: str = "text-embedding-3-small", dimensions: int = 1536) -> None:
        self.model = model
        self.dimensions = dimensions
        self.total_tokens = 0

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            vectors.append([digest[i % len(digest)] / 255 for i in range(self.dimensions)])
            self.total_tokens += len(text.split())
        return vectors

"""단위 테스트 공용 픽스처 — DB가 필요한 저장 계층은 인메모리 SQLite로 대신한다."""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.domain.tables import AI_SCHEMA, Base, Source


@pytest.fixture()
def session() -> Iterator[Session]:
    """ai 스키마 테이블과 카탈로그 2행이 있는 SQLite 세션."""
    engine = create_engine("sqlite://").execution_options(schema_translate_map={AI_SCHEMA: None})
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        for key, version, repo, ref, path, fmt, adapter in [
            ("langchain_v03", "v0.3", "langchain-ai/langchain", "v0.3", "docs/docs/",
             "DOCUSAURUS", "DocusaurusAdapter"),
            ("langchain_v1x", "v1.x", "langchain-ai/docs", "main", "src/oss/",
             "MINTLIFY", "MintlifyAdapter"),
        ]:  # fmt: skip
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
        yield db
    engine.dispose()

from pathlib import Path
from typing import Literal, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

# 정책서 §9.1 프로필별 기능 매트릭스의 프로필 집합
AppProfile = Literal["local", "staging", "loadtest", "prod"]


class Settings(BaseSettings):
    """애플리케이션 설정 — 환경 변수에서 비밀값·실행 프로필·DB 접속 정보를 로드.

    top_k, temperature 같은 비비밀 파라미터는 configs/*.yaml 에서 로딩 (settings.py 대상 아님).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # .env에 알 수 없는 키가 있어도 무시 (오류 방지)
    )

    # 실행 프로필 (APP_PROFILE)
    app_profile: AppProfile = "local"

    # 수집·임베딩 경로 활성화 (INGEST_ENABLED) — prod에서는 반드시 꺼져 있어야 함
    ingest_enabled: bool = False

    # 수집 원본·리포트 저장 루트 (INGEST_DATA_DIR) — Git에 올리지 않는다 (data-sources.md §2)
    ingest_data_dir: Path = Path("data")

    # Chroma 임베디드 저장 경로 (CHROMA_DATA_DIR) — ADR-002
    chroma_data_dir: Path = Path("data/chroma")

    # 검증 게이트 permalink 전수 검증용 GitHub 토큰 (GITHUB_TOKEN, 선택) — 정책서 §4.4
    github_token: str = ""

    # 생성 단계를 고정 토큰으로 대체하는 mock LLM (LLM_MOCK) — local·loadtest 전용
    llm_mock: bool = False

    # OpenAI API 키
    openai_api_key: str = ""

    # ai-server ↔ backend 내부 인증 토큰
    # backend가 RAG 엔드포인트 호출 시 X-Internal-Token 헤더에 첨부
    internal_token: str = ""

    # PostgreSQL 접속 정보 — ai 스키마는 ai-server(Alembic)가 소유
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "contextq_db"
    postgres_user: str = "contextq"
    postgres_password: str = ""

    @model_validator(mode="after")
    def _forbid_unsafe_features_in_prod(self) -> Self:
        """INV-17: prod에서 수집·임베딩 또는 mock LLM 설정이 감지되면 기동을 실패시킨다."""
        if self.app_profile != "prod":
            return self
        enabled = [
            name
            for name, on in (("INGEST_ENABLED", self.ingest_enabled), ("LLM_MOCK", self.llm_mock))
            if on
        ]
        if enabled:
            raise ValueError(
                f"INV-17: prod 프로필에서 허용되지 않는 설정이 켜져 있습니다: {', '.join(enabled)}"
            )
        return self

    @property
    def docs_enabled(self) -> bool:
        """FastAPI /docs 노출 여부 — prod에서는 내부망에서도 노출하지 않는다 (정책서 §9.1)."""
        return self.app_profile != "prod"

    @property
    def database_url(self) -> str:
        """SQLAlchemy 접속 URL (psycopg 3 드라이버). 비밀번호의 특수문자는 URL 인코딩된다."""
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        ).render_as_string(hide_password=False)


# 모듈 수준 싱글톤 — 다른 모듈에서 `from src.config.settings import settings`로 사용
# 검증 실패(INV-17) 시 import 시점에 예외가 발생해 프로세스가 기동하지 않는다
settings = Settings()

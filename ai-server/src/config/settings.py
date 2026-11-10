from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """애플리케이션 설정 — .env에서 비밀값만 로드.

    top_k, temperature 같은 비비밀 파라미터는 configs/*.yaml 에서 로딩 (settings.py 대상 아님).
    비밀값(API 키, 토큰)만 이 클래스에서 관리.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # .env에 알 수 없는 키가 있어도 무시 (오류 방지)
    )

    # OpenAI API 키
    openai_api_key: str = ""

    # ai-server ↔ backend 내부 인증 토큰
    # backend가 RAG 엔드포인트 호출 시 X-Internal-Token 헤더에 첨부
    internal_token: str = ""


# 모듈 수준 싱글톤 — 다른 모듈에서 `from src.config.settings import settings`로 사용
settings = Settings()

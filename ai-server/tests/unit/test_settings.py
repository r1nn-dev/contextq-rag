import pytest
from pydantic import ValidationError

from src.config.settings import Settings


def _settings(**overrides: object) -> Settings:
    # .env 파일 영향을 받지 않도록 env_file을 끄고 생성
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


@pytest.mark.parametrize("profile", ["local", "staging", "loadtest", "prod"])
def test_all_policy_profiles_are_accepted(profile: str) -> None:
    assert _settings(app_profile=profile).app_profile == profile


def test_unknown_profile_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _settings(app_profile="dev")


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        ({"ingest_enabled": True}, "INGEST_ENABLED"),
        ({"llm_mock": True}, "LLM_MOCK"),
        ({"ingest_enabled": True, "llm_mock": True}, "INGEST_ENABLED, LLM_MOCK"),
    ],
)
def test_prod_fails_fast_when_unsafe_feature_enabled(flags: dict[str, bool], expected: str) -> None:
    with pytest.raises(ValidationError, match=f"INV-17.*{expected}"):
        _settings(app_profile="prod", **flags)


def test_prod_starts_when_unsafe_features_disabled() -> None:
    settings = _settings(app_profile="prod")
    assert settings.ingest_enabled is False
    assert settings.llm_mock is False


@pytest.mark.parametrize("profile", ["local", "loadtest"])
def test_non_prod_profiles_allow_ingest_and_mock(profile: str) -> None:
    settings = _settings(app_profile=profile, ingest_enabled=True, llm_mock=True)
    assert settings.ingest_enabled and settings.llm_mock


def test_profile_and_flags_are_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_PROFILE", "prod")
    monkeypatch.setenv("LLM_MOCK", "true")
    with pytest.raises(ValidationError, match="LLM_MOCK"):
        _settings()


def test_docs_hidden_only_in_prod() -> None:
    assert _settings(app_profile="local").docs_enabled is True
    assert _settings(app_profile="prod").docs_enabled is False


def test_database_url_uses_psycopg_driver() -> None:
    settings = _settings(
        postgres_host="db",
        postgres_port=5433,
        postgres_db="contextq_db",
        postgres_user="u",
        postgres_password="p@ss",
    )
    # 비밀번호의 '@'가 URL 구분자로 해석되지 않도록 인코딩된다
    assert settings.database_url == "postgresql+psycopg://u:p%40ss@db:5433/contextq_db"

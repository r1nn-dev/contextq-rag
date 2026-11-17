"""수집 CLI — 프로필·플래그에 따른 명령 등록 (정책서 §4.5, INV-17)."""

import pytest

from src.config.settings import Settings
from src.ingest.cli import build_parser, ingest_allowed, main


def _settings(profile: str, ingest_enabled: bool) -> Settings:
    return Settings(_env_file=None, app_profile=profile, ingest_enabled=ingest_enabled)  # type: ignore[call-arg, arg-type]


@pytest.mark.parametrize(
    ("profile", "enabled", "allowed"),
    [
        ("local", True, True),
        ("staging", True, True),
        ("loadtest", True, True),
        ("local", False, False),
        ("prod", False, False),
    ],
)
def test_ingest_allowed(profile: str, enabled: bool, allowed: bool) -> None:
    assert ingest_allowed(_settings(profile, enabled)) is allowed


def test_ingest_command_registered_only_when_allowed() -> None:
    allowed = build_parser(_settings("local", True)).parse_args(["ingest", "--source", "k"])
    assert allowed.command == "ingest"
    with pytest.raises(SystemExit):
        build_parser(_settings("local", False)).parse_args(["ingest", "--source", "k"])


@pytest.mark.parametrize(("profile", "enabled"), [("prod", False), ("local", False)])
def test_main_rejects_ingest_with_forbidden_message(
    profile: str, enabled: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["ingest", "--source", "langchain_v03"], _settings(profile, enabled)) == 2
    assert "FORBIDDEN_IN_PROFILE" in capsys.readouterr().err

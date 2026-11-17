"""활성화·롤백 후 reload 호출 — 실패해도 명령은 성공, 경고만 (정책서 §4.5)."""

import httpx
import pytest

from src.config.settings import Settings
from src.ingest.activation import ActivationResult
from src.ingest.cli import _print_activation
from src.ingest.reload import notify_reload


def client(handler: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(transport=handler)


def test_notify_reload_posts_source_with_token() -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"sourceKey": "langchain_v1x", "activeRunId": 4})

    failure = notify_reload(
        "http://ai:8000/", "tok", "langchain_v1x", client=client(httpx.MockTransport(handle))
    )

    assert failure is None
    [request] = seen
    assert str(request.url) == "http://ai:8000/internal/v1/index/reload"
    assert request.headers["X-Internal-Token"] == "tok"
    assert request.read() == b'{"sourceKey":"langchain_v1x"}'


def test_notify_reload_reports_http_error_code() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"code": "INTERNAL_UNAUTHORIZED"})

    failure = notify_reload("http://ai:8000", "", "x", client=client(httpx.MockTransport(handle)))

    assert failure == "HTTP 401 INTERNAL_UNAUTHORIZED"


def test_notify_reload_never_raises_on_connection_error() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    failure = notify_reload("http://ai:8000", "t", "x", client=client(httpx.MockTransport(handle)))

    assert failure is not None and failure.startswith("ConnectError")


RESULT = ActivationResult("langchain_v1x", 4, superseded=[3], purged=[1])
SETTINGS = Settings(_env_file=None, internal_token="tok")  # type: ignore[call-arg]


def test_activation_output_reports_reload(capsys: pytest.CaptureFixture[str]) -> None:
    calls: list[tuple[str, str, str]] = []

    def notify(url: str, token: str, source_key: str) -> str | None:
        calls.append((url, token, source_key))
        return None

    _print_activation("activate", RESULT, SETTINGS, notify)

    assert calls == [("http://localhost:8000", "tok", "langchain_v1x")]
    out = capsys.readouterr()
    assert "run 4 ACTIVE" in out.out and "reload 완료" in out.out
    assert out.err == ""


def test_activation_reload_failure_is_only_a_warning(capsys: pytest.CaptureFixture[str]) -> None:
    _print_activation("rollback", RESULT, SETTINGS, lambda *_: "ConnectError: refused")

    err = capsys.readouterr().err
    assert "경고" in err and "30초" in err

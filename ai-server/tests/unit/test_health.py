from fastapi.testclient import TestClient

from src.config.settings import Settings
from src.main import create_app


def _client(profile: str) -> TestClient:
    return TestClient(create_app(Settings(_env_file=None, app_profile=profile)))  # type: ignore[call-arg]


def test_internal_health_returns_ok() -> None:
    response = _client("local").get("/internal/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_docs_exposed_outside_prod() -> None:
    client = _client("local")

    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_docs_hidden_in_prod() -> None:
    client = _client("prod")

    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/internal/v1/health").status_code == 200

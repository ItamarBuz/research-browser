from fastapi import APIRouter
from fastapi.testclient import TestClient

from rb_engine import API_VERSION
from rb_engine.api.app import create_app
from rb_engine.domain.errors import ModelNotReadyError
from rb_engine.runtime.container import EngineServices
from rb_engine.runtime.settings import EngineSettings


def test_health_requires_token(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 401


def test_health_rejects_wrong_token(client: TestClient) -> None:
    response = client.get("/health", headers={"Authorization": "Bearer wrong-token-0000000"})
    assert response.status_code == 401


def test_health_ok_with_token(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get("/health", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["api_version"] == API_VERSION


def test_cors_preflight_allows_tauri_origin(client: TestClient) -> None:
    response = client.options(
        "/health",
        headers={
            "Origin": "http://tauri.localhost",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://tauri.localhost"


def test_cors_rejects_unknown_origin(client: TestClient) -> None:
    response = client.options(
        "/health",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in response.headers


def test_engine_error_renders_problem_json(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    router = APIRouter()

    @router.get("/boom")
    def boom() -> None:
        raise ModelNotReadyError("embedding model is still downloading")

    client.app.include_router(router)  # type: ignore[attr-defined]
    response = client.get("/boom", headers=auth_headers)

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json() == {
        "type": "urn:rb-engine:problem:model-not-ready",
        "title": "Model not ready",
        "status": 503,
        "detail": "embedding model is still downloading",
    }


def test_unexpected_error_hides_internals(
    auth_headers: dict[str, str], services: EngineServices
) -> None:
    settings = EngineSettings(port=8765, token=auth_headers["Authorization"][7:])
    app = create_app(settings, lambda: services)

    @app.get("/crash")
    def crash() -> None:
        raise RuntimeError("secret path C:/internal")

    response = TestClient(app, raise_server_exceptions=False).get("/crash", headers=auth_headers)
    assert response.status_code == 500
    assert "secret" not in response.text

import time

from fastapi.testclient import TestClient

from rb_engine.runtime.container import EngineServices


def test_system_reports_hardware_and_tier(client: TestClient, auth_headers: dict[str, str]) -> None:
    body = client.get("/system", headers=auth_headers).json()

    assert body["hardware"]["cpu_logical_cores"] == 8
    assert body["tier"]["detected"] == "standard"
    assert body["tier"]["effective"] == "standard"
    assert body["tier"]["override_source"] is None
    assert body["resident_model_limit"] == 2


def test_tier_override_is_applied_and_persisted(
    client: TestClient, auth_headers: dict[str, str], services: EngineServices
) -> None:
    body = client.put("/system/tier-override", json={"tier": "pro"}, headers=auth_headers).json()

    assert body["tier"]["effective"] == "pro"
    assert body["tier"]["override_source"] == "user"
    assert body["resident_model_limit"] == 4
    assert services.preferences.load().tier_override == "pro"

    body = client.put("/system/tier-override", json={"tier": None}, headers=auth_headers).json()
    assert body["tier"]["effective"] == "standard"
    assert body["tier"]["override_source"] is None


def test_tier_override_rejects_unknown_tier(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.put("/system/tier-override", json={"tier": "ultra"}, headers=auth_headers)
    assert response.status_code == 422


def test_models_lists_recommended_first(client: TestClient, auth_headers: dict[str, str]) -> None:
    body = client.get("/models", headers=auth_headers).json()

    assert body["tier"] == "standard"
    assert [(m["id"], m["recommended"]) for m in body["models"]] == [
        ("embed-test", True),
        ("llm-test", False),
    ]
    assert body["models"][0]["state"]["status"] == "not_downloaded"


def test_download_unknown_model_is_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post("/models/nope/download", headers=auth_headers)
    assert response.status_code == 404
    assert response.json()["type"] == "urn:rb-engine:problem:model-not-found"


def test_download_runs_in_background_until_ready(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.post("/models/embed-test/download", headers=auth_headers)
    assert response.status_code == 202

    deadline = time.monotonic() + 5
    status = ""
    while time.monotonic() < deadline:
        models = client.get("/models", headers=auth_headers).json()["models"]
        status = next(m for m in models if m["id"] == "embed-test")["state"]["status"]
        if status == "ready":
            break
        time.sleep(0.02)
    assert status == "ready"

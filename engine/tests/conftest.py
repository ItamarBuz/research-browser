import pytest
from fastapi.testclient import TestClient

from rb_engine.api.app import create_app
from rb_engine.runtime.settings import EngineSettings

TEST_TOKEN = "test-token-0123456789"


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(EngineSettings(port=8765, token=TEST_TOKEN)))


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TEST_TOKEN}"}

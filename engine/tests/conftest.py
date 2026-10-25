from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rb_engine.api.app import create_app
from rb_engine.runtime.container import EngineServices, build_services
from rb_engine.runtime.paths import DataPaths
from rb_engine.runtime.settings import EngineSettings
from tests.fakes import EMBED_FILES, LLM_FILES, FakeModelHost, hardware, sample_catalog

TEST_TOKEN = "test-token-0123456789"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def model_host() -> FakeModelHost:
    return FakeModelHost.for_catalog(sample_catalog(), EMBED_FILES | LLM_FILES)


@pytest.fixture
def services(tmp_path: Path, model_host: FakeModelHost) -> EngineServices:
    return build_services(
        DataPaths(tmp_path),
        hardware=hardware(ram_gb=16),  # Standard tier
        catalog=sample_catalog(),
        transport=model_host.transport(),
    )


@pytest.fixture
def client(services: EngineServices) -> Iterator[TestClient]:
    app = create_app(EngineSettings(port=8765, token=TEST_TOKEN), lambda: services)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TEST_TOKEN}"}

import asyncio
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import NamedTuple

import pytest

from rb_engine.domain.errors import (
    InsufficientDiskSpaceError,
    ModelIntegrityError,
    ModelNotReadyError,
)
from rb_engine.runtime.model_manager import (
    MARKER_NAME,
    ModelManager,
    ModelStatus,
    bytes_on_disk,
)
from tests.fakes import EMBED_FILES, LLM_FILES, FakeModelHost, sample_catalog

pytestmark = pytest.mark.anyio


def _manager(tmp_path: Path, host: FakeModelHost) -> ModelManager:
    return ModelManager(sample_catalog(), tmp_path, transport=host.transport(), retry_delay_s=0)


@pytest.fixture
def host() -> FakeModelHost:
    return FakeModelHost.for_catalog(sample_catalog(), EMBED_FILES | LLM_FILES)


async def test_downloads_and_verifies(tmp_path: Path, host: FakeModelHost) -> None:
    manager = _manager(tmp_path, host)
    assert manager.state("embed-test").status == ModelStatus.NOT_DOWNLOADED

    model_dir = await manager.ensure("embed-test")

    assert (model_dir / "onnx" / "model.onnx").read_bytes() == EMBED_FILES["onnx/model.onnx"]
    assert (model_dir / MARKER_NAME).is_file()
    state = manager.state("embed-test")
    assert state.status == ModelStatus.READY
    assert state.downloaded_bytes == state.total_bytes
    assert manager.path_of("embed-test") == model_dir


async def test_ready_state_survives_restart(tmp_path: Path, host: FakeModelHost) -> None:
    await _manager(tmp_path, host).ensure("embed-test")
    host.requests.clear()

    fresh = _manager(tmp_path, host)
    assert fresh.state("embed-test").status == ModelStatus.READY
    await fresh.ensure("embed-test")
    assert host.requests == []


async def test_path_of_requires_ready(tmp_path: Path, host: FakeModelHost) -> None:
    with pytest.raises(ModelNotReadyError):
        _manager(tmp_path, host).path_of("embed-test")


async def test_corrupt_download_is_rejected_and_deleted(
    tmp_path: Path, host: FakeModelHost
) -> None:
    host.corrupt = True
    manager = _manager(tmp_path, host)

    with pytest.raises(ModelIntegrityError):
        await manager.ensure("llm-test")

    state = manager.state("llm-test")
    assert state.status == ModelStatus.FAILED
    assert state.error is not None
    assert "verification" in state.error
    assert not list(tmp_path.rglob("*.part"))
    assert not list(tmp_path.rglob("llm.gguf"))


async def test_failed_download_can_be_retried(tmp_path: Path, host: FakeModelHost) -> None:
    host.corrupt = True
    manager = _manager(tmp_path, host)
    with pytest.raises(ModelIntegrityError):
        await manager.ensure("llm-test")

    host.corrupt = False
    await manager.ensure("llm-test")
    assert manager.state("llm-test").status == ModelStatus.READY


class _Partial(NamedTuple):
    manager: ModelManager
    part: Path
    half: int


def _with_half_downloaded(tmp_path: Path, host: FakeModelHost) -> _Partial:
    manager = _manager(tmp_path, host)
    spec = sample_catalog().get("llm-test")
    part = manager.model_dir(spec) / "llm.gguf.part"
    part.parent.mkdir(parents=True)
    half = len(LLM_FILES["llm.gguf"]) // 2
    part.write_bytes(LLM_FILES["llm.gguf"][:half])
    return _Partial(manager, part, half)


async def test_resumes_partial_download(tmp_path: Path, host: FakeModelHost) -> None:
    manager, _, half = _with_half_downloaded(tmp_path, host)

    await manager.ensure("llm-test")

    assert host.requests[0].headers["Range"] == f"bytes={half}-"
    assert manager.state("llm-test").status == ModelStatus.READY


async def test_counts_partial_files_as_progress(tmp_path: Path, host: FakeModelHost) -> None:
    manager, _, half = _with_half_downloaded(tmp_path, host)
    spec = sample_catalog().get("llm-test")
    assert bytes_on_disk(spec, manager.model_dir(spec)) == half


async def test_restarts_when_server_ignores_range(tmp_path: Path, host: FakeModelHost) -> None:
    host.honour_range = False
    manager, _, _ = _with_half_downloaded(tmp_path, host)

    model_dir = await manager.ensure("llm-test")

    assert (model_dir / "llm.gguf").read_bytes() == LLM_FILES["llm.gguf"]


async def test_retries_transient_network_errors(tmp_path: Path, host: FakeModelHost) -> None:
    host.fail_first = 2
    manager = _manager(tmp_path, host)

    await manager.ensure("llm-test")

    assert manager.state("llm-test").status == ModelStatus.READY
    assert len(host.requests) == 3


async def test_refuses_when_disk_is_full(
    tmp_path: Path, host: FakeModelHost, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, "disk_usage", lambda _path: SimpleNamespace(free=1024))
    manager = _manager(tmp_path, host)

    with pytest.raises(InsufficientDiskSpaceError):
        await manager.ensure("llm-test")
    assert manager.state("llm-test").status == ModelStatus.FAILED


async def test_concurrent_requests_share_one_download(tmp_path: Path, host: FakeModelHost) -> None:
    manager = _manager(tmp_path, host)

    await asyncio.gather(*(manager.ensure("llm-test") for _ in range(5)))

    assert len(host.requests) == 1

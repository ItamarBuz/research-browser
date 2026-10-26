"""Test doubles: fake hardware, a tiny model catalog and an in-memory model host."""

import hashlib
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import httpx

from rb_engine.domain.catalog import ModelFile, ModelRole, ModelSpec
from rb_engine.domain.hardware import GpuInfo, HardwareProfile, Tier
from rb_engine.runtime.catalog import ModelCatalog

GB_MB = 1024


def hardware(
    ram_gb: float = 16, gpus: list[GpuInfo] | None = None, os: str = "Windows"
) -> HardwareProfile:
    """Simulates what the OS reports: slightly less RAM than the marketed size."""
    total_mb = int(ram_gb * GB_MB) - 300
    return HardwareProfile(
        os=os,
        arch="AMD64",
        cpu_physical_cores=4,
        cpu_logical_cores=8,
        total_ram_mb=total_mb,
        available_ram_mb=total_mb // 2,
        gpus=gpus or [],
    )


def nvidia(memory_gb: int) -> GpuInfo:
    return GpuInfo(
        name="NVIDIA Test", backend="cuda", memory_mb=memory_gb * GB_MB, unified_memory=False
    )


def model(
    model_id: str,
    files: dict[str, bytes],
    *,
    role: ModelRole = ModelRole.EMBEDDER,
    tiers: tuple[Tier, ...] = (Tier.STANDARD,),
) -> ModelSpec:
    return ModelSpec(
        id=model_id,
        name=model_id.title(),
        role=role,
        tiers=tiers,
        repo=f"test/{model_id}",
        revision="a" * 40,
        license="mit",
        files=tuple(
            ModelFile(path=p, sha256=hashlib.sha256(c).hexdigest(), size_bytes=len(c))
            for p, c in files.items()
        ),
    )


EMBED_FILES = {"onnx/model.onnx": b"embedding-weights" * 1000, "tokenizer.json": b'{"t": 1}'}
LLM_FILES = {"llm.gguf": b"gguf-weights" * 2000}


def sample_catalog() -> ModelCatalog:
    return ModelCatalog(
        [
            model("embed-test", EMBED_FILES),
            model("llm-test", LLM_FILES, role=ModelRole.LLM, tiers=()),
        ]
    )


@dataclass
class FakeModelHost:
    """Serves catalog files by download URL, honouring Range like Hugging Face does."""

    content: dict[str, bytes]
    honour_range: bool = True
    fail_first: int = 0
    fail_midway: int = 0
    """Requests that send a slice of the file and then drop the connection."""
    timeout_first: int = 0
    corrupt: bool = False
    requests: list[httpx.Request] = field(default_factory=list)

    @classmethod
    def for_catalog(cls, catalog: ModelCatalog, files: dict[str, bytes]) -> "FakeModelHost":
        by_url = {spec.download_url(f): files[f.path] for spec in catalog.all() for f in spec.files}
        return cls(content=by_url)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.fail_first > 0:
            self.fail_first -= 1
            raise httpx.ConnectError("connection reset", request=request)
        if self.timeout_first > 0:
            self.timeout_first -= 1
            raise httpx.ReadTimeout("", request=request)  # httpx timeouts often have no text
        body = self.content.get(str(request.url))
        if body is None:
            return httpx.Response(404)
        if self.corrupt:
            body = b"x" * len(body)
        range_header = request.headers.get("Range")
        start = 0
        if range_header and self.honour_range:
            start = int(range_header.removeprefix("bytes=").rstrip("-"))
        status = 206 if start else 200
        if self.fail_midway > 0:
            self.fail_midway -= 1
            return httpx.Response(status, stream=_DroppingStream(body[start : start + 1000]))
        return httpx.Response(status, content=body[start:])


class _DroppingStream(httpx.AsyncByteStream):
    """Sends some bytes, then fails like a dropped connection."""

    def __init__(self, chunk: bytes) -> None:
        self._chunk = chunk

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield self._chunk
        raise httpx.ReadError("connection dropped")

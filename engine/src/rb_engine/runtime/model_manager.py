"""Downloads, verifies and locates local model files.

Layout: `<models_dir>/<model id>/<revision>/<file path>`, plus a `.verified` marker written
only after every file matched its pinned SHA-256, so startup never re-hashes gigabytes.
Interrupted downloads resume from `<file>.part` with an HTTP Range request.
"""

import asyncio
import hashlib
import json
import logging
import shutil
from enum import StrEnum
from pathlib import Path

import httpx
from pydantic import BaseModel

from rb_engine.domain.catalog import ModelFile, ModelSpec
from rb_engine.domain.errors import (
    EngineError,
    InsufficientDiskSpaceError,
    ModelIntegrityError,
    ModelNotReadyError,
    SourceUnavailableError,
)
from rb_engine.runtime.catalog import ModelCatalog

logger = logging.getLogger(__name__)

MARKER_NAME = ".verified"
DISK_HEADROOM_BYTES = 512 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024
MAX_ATTEMPTS = 4
HTTP_PARTIAL_CONTENT = 206


class ModelStatus(StrEnum):
    NOT_DOWNLOADED = "not_downloaded"
    DOWNLOADING = "downloading"
    READY = "ready"
    FAILED = "failed"


class ModelState(BaseModel):
    status: ModelStatus
    downloaded_bytes: int
    total_bytes: int
    error: str | None = None


class ModelManager:
    def __init__(
        self,
        catalog: ModelCatalog,
        models_dir: Path,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        retry_delay_s: float = 2.0,
    ) -> None:
        self._catalog = catalog
        self._models_dir = models_dir
        self._transport = transport
        self._retry_delay_s = retry_delay_s
        self._tasks: dict[str, asyncio.Task[Path]] = {}
        self._progress: dict[str, int] = {}
        self._errors: dict[str, str] = {}

    # --- queries -------------------------------------------------------------------------

    def model_dir(self, spec: ModelSpec) -> Path:
        return self._models_dir / spec.id / spec.revision

    def is_ready(self, spec: ModelSpec) -> bool:
        marker = self.model_dir(spec) / MARKER_NAME
        try:
            verified = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        expected = {f.path: f.sha256 for f in spec.files}
        return bool(verified == expected) and all(
            (self.model_dir(spec) / f.path).is_file() for f in spec.files
        )

    def state(self, model_id: str) -> ModelState:
        spec = self._catalog.get(model_id)
        total = spec.size_bytes
        task = self._tasks.get(model_id)
        if task is not None and not task.done():
            return ModelState(
                status=ModelStatus.DOWNLOADING,
                downloaded_bytes=self._progress.get(model_id, 0),
                total_bytes=total,
            )
        if self.is_ready(spec):
            return ModelState(status=ModelStatus.READY, downloaded_bytes=total, total_bytes=total)
        if model_id in self._errors:
            return ModelState(
                status=ModelStatus.FAILED,
                downloaded_bytes=self._progress.get(model_id, 0),
                total_bytes=total,
                error=self._errors[model_id],
            )
        return ModelState(status=ModelStatus.NOT_DOWNLOADED, downloaded_bytes=0, total_bytes=total)

    def path_of(self, model_id: str) -> Path:
        """Directory of a ready model; consumers load files relative to it."""
        spec = self._catalog.get(model_id)
        if not self.is_ready(spec):
            raise ModelNotReadyError(f"Model {model_id!r} is not downloaded yet")
        return self.model_dir(spec)

    # --- downloads -----------------------------------------------------------------------

    def start_download(self, model_id: str) -> None:
        """Begin downloading in the background; a no-op if running or already ready."""
        spec = self._catalog.get(model_id)
        running = self._tasks.get(model_id)
        if (running is not None and not running.done()) or self.is_ready(spec):
            return
        self._errors.pop(model_id, None)
        task = asyncio.create_task(self._download(spec), name=f"download:{model_id}")
        task.add_done_callback(lambda t: self._record_failure(model_id, t))
        self._tasks[model_id] = task

    async def ensure(self, model_id: str) -> Path:
        """Download (or wait for the running download) and return the model directory."""
        self.start_download(model_id)
        task = self._tasks.get(model_id)
        if task is not None:
            await asyncio.shield(task)
        return self.path_of(model_id)

    def _record_failure(self, model_id: str, task: asyncio.Task[Path]) -> None:
        if task.cancelled():
            self._errors[model_id] = "Download cancelled"
            return
        exc = task.exception()
        if exc is None:
            return
        if not isinstance(exc, EngineError):
            logger.error("Download of %s failed", model_id, exc_info=exc)
        self._errors[model_id] = exc.detail if isinstance(exc, EngineError) else str(exc)

    async def _download(self, spec: ModelSpec) -> Path:
        target = self.model_dir(spec)
        target.mkdir(parents=True, exist_ok=True)
        self._check_disk_space(spec, target)
        done_bytes = sum(f.size_bytes for f in spec.files if (target / f.path).is_file())
        # Count partial files too, so a resumed download does not briefly report 0%.
        self._progress[spec.id] = bytes_on_disk(spec, target)

        async with httpx.AsyncClient(
            transport=self._transport,
            follow_redirects=True,
            timeout=httpx.Timeout(30.0, read=120.0),
        ) as client:
            for file in spec.files:
                if (target / file.path).is_file():
                    continue  # verified when it was moved into place
                await self._download_file(client, spec, file, target, done_bytes)
                done_bytes += file.size_bytes

        marker = {f.path: f.sha256 for f in spec.files}
        (target / MARKER_NAME).write_text(json.dumps(marker, indent=2), encoding="utf-8")
        logger.info("Model %s ready at %s", spec.id, target)
        return target

    def _check_disk_space(self, spec: ModelSpec, target: Path) -> None:
        remaining = max(spec.size_bytes - bytes_on_disk(spec, target), 0)
        free = shutil.disk_usage(target).free
        if free < remaining + DISK_HEADROOM_BYTES:
            raise InsufficientDiskSpaceError(
                f"{spec.name} needs {_gb(remaining)} GB free; only {_gb(free)} GB available"
            )

    async def _download_file(
        self,
        client: httpx.AsyncClient,
        spec: ModelSpec,
        file: ModelFile,
        target: Path,
        done_before: int,
    ) -> None:
        final = target / file.path
        part = _part_path(final)
        part.parent.mkdir(parents=True, exist_ok=True)
        url = spec.download_url(file)

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                await self._stream_to_part(client, url, part, spec.id, done_before)
                break
            except httpx.TransportError as exc:
                if attempt == MAX_ATTEMPTS:
                    raise SourceUnavailableError(f"Download of {file.path} failed: {exc}") from exc
                logger.warning("Retrying %s after %s (attempt %d)", file.path, exc, attempt)
                await asyncio.sleep(self._retry_delay_s * attempt)

        digest = await asyncio.to_thread(_sha256_of, part)
        if digest != file.sha256:
            part.unlink(missing_ok=True)
            raise ModelIntegrityError(
                f"{file.path} failed verification (expected {file.sha256[:12]}…, "
                f"got {digest[:12]}…); it was deleted, please retry"
            )
        part.replace(final)

    async def _stream_to_part(
        self, client: httpx.AsyncClient, url: str, part: Path, model_id: str, done_before: int
    ) -> None:
        offset = part.stat().st_size if part.is_file() else 0
        headers = {"Range": f"bytes={offset}-"} if offset else {}
        async with client.stream("GET", url, headers=headers) as response:
            if response.status_code >= httpx.codes.BAD_REQUEST:
                raise SourceUnavailableError(
                    f"Model host answered HTTP {response.status_code} for {url}"
                )
            if offset and response.status_code != HTTP_PARTIAL_CONTENT:
                offset = 0  # server ignored the Range header; start over
            with part.open("ab" if offset else "wb") as out:
                written = offset
                async for chunk in response.aiter_bytes(CHUNK_BYTES):
                    out.write(chunk)
                    written += len(chunk)
                    self._progress[model_id] = done_before + written


def _part_path(final: Path) -> Path:
    return final.with_name(final.name + ".part")


def bytes_on_disk(spec: ModelSpec, target: Path) -> int:
    """Bytes already present for a model: finished files plus partial downloads."""
    total = 0
    for f in spec.files:
        final, part = target / f.path, _part_path(target / f.path)
        if final.is_file():
            total += f.size_bytes
        elif part.is_file():
            total += min(part.stat().st_size, f.size_bytes)
    return total


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _gb(n_bytes: int) -> str:
    return f"{n_bytes / 1024**3:.1f}"

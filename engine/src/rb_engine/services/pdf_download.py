"""Downloads an open-access PDF found online, with the same checks as an upload."""

import hashlib
import tempfile
from pathlib import Path

import httpx

from rb_engine.adapters.sources.http import USER_AGENT
from rb_engine.domain.errors import EngineError

MAX_PDF_BYTES = 300 * 1024 * 1024
PDF_MAGIC = b"%PDF-"


class PdfDownloadError(EngineError):
    status_code = 502
    title = "Could not download the PDF"
    type_slug = "pdf-download"


BLOCKED_STATUSES = frozenset({401, 403, 429})
GONE_STATUSES = frozenset({404, 410})
MANUAL_HINT = "Use Open to get the PDF in your browser, then import it in the Library."


def _check_status(response: httpx.Response) -> None:
    status = response.status_code
    if status == httpx.codes.OK:
        return
    if status in BLOCKED_STATUSES:
        raise PdfDownloadError(
            f"The publisher does not allow automatic downloads (HTTP {status}). {MANUAL_HINT}"
        )
    if status in GONE_STATUSES:
        raise PdfDownloadError(f"The PDF link no longer works (HTTP {status}). {MANUAL_HINT}")
    raise PdfDownloadError(f"The server answered HTTP {status}. {MANUAL_HINT}")


def _check_chunk(chunk: bytes, size_before: int) -> None:
    if size_before == 0 and not chunk.startswith(PDF_MAGIC):
        raise PdfDownloadError(f"The link leads to a web page, not a PDF. {MANUAL_HINT}")
    if size_before + len(chunk) > MAX_PDF_BYTES:
        raise PdfDownloadError("The PDF is larger than 300 MB")


def _check_not_empty(size: int) -> None:
    if size == 0:
        raise PdfDownloadError("The server sent an empty file")


async def download_pdf(
    url: str, incoming: Path, *, transport: httpx.AsyncBaseTransport | None = None
) -> tuple[Path, str, int]:
    """Stream `url` into `incoming`; returns (path, sha256, size)."""
    if not url.startswith(("https://", "http://")):
        raise PdfDownloadError("Only web (http/https) links can be downloaded")
    incoming.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    with tempfile.NamedTemporaryFile(dir=incoming, suffix=".part", delete=False) as out:
        path = Path(out.name)
    try:
        async with (
            httpx.AsyncClient(
                transport=transport,
                follow_redirects=True,
                timeout=httpx.Timeout(60.0, connect=10.0),
                headers={"User-Agent": USER_AGENT, "Accept": "application/pdf"},
            ) as client,
            client.stream("GET", url) as response,
        ):
            _check_status(response)
            with path.open("wb") as file:
                async for chunk in response.aiter_bytes(1024 * 1024):
                    _check_chunk(chunk, size)
                    size += len(chunk)
                    digest.update(chunk)
                    file.write(chunk)
        _check_not_empty(size)
    except httpx.TransportError as exc:
        path.unlink(missing_ok=True)
        raise PdfDownloadError(f"Cannot connect: {exc}") from exc
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path, digest.hexdigest(), size

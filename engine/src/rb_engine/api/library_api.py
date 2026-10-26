"""Library endpoints: import PDFs, list, delete, re-index and search."""

import hashlib
import tempfile
from pathlib import Path

from fastapi import APIRouter, Response, UploadFile, status
from pydantic import BaseModel

from rb_engine.api.deps import Services
from rb_engine.domain.errors import DocumentNotFoundError
from rb_engine.domain.library import (
    Document,
    IndexStatus,
    LibraryState,
    SearchRequest,
    SearchResponse,
)

router = APIRouter(prefix="/library", tags=["library"])

MAX_UPLOAD_BYTES = 300 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024
PDF_MAGIC = b"%PDF-"


class ImportResult(BaseModel):
    file_name: str
    document: Document | None = None
    error: str | None = None


class _RejectedUploadError(Exception):
    pass


def _safe_name(upload: UploadFile) -> str:
    return Path(upload.filename or "document.pdf").name or "document.pdf"


def _check_chunk(chunk: bytes, size_before: int) -> None:
    if size_before == 0 and not chunk.startswith(PDF_MAGIC):
        raise _RejectedUploadError("Not a PDF file")
    if size_before + len(chunk) > MAX_UPLOAD_BYTES:
        raise _RejectedUploadError(f"File is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")


def _check_complete(size: int) -> None:
    if size == 0:
        raise _RejectedUploadError("The file is empty")


async def _receive(upload: UploadFile, incoming: Path) -> tuple[Path, str, int]:
    """Stream an upload to disk, hashing as it goes. Returns (path, sha256, size)."""
    incoming.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    with tempfile.NamedTemporaryFile(dir=incoming, suffix=".part", delete=False) as out:
        path = Path(out.name)
        try:
            while chunk := await upload.read(UPLOAD_CHUNK_BYTES):
                _check_chunk(chunk, size)
                size += len(chunk)
                digest.update(chunk)
                out.write(chunk)
            _check_complete(size)
        except BaseException:
            out.close()
            path.unlink(missing_ok=True)
            raise
    return path, digest.hexdigest(), size


@router.get("", operation_id="getLibrary")
def get_library(services: Services) -> LibraryState:
    return services.library.state()


@router.post("/documents", operation_id="importDocuments")
async def import_documents(files: list[UploadFile], services: Services) -> list[ImportResult]:
    results: list[ImportResult] = []
    for upload in files:
        name = _safe_name(upload)
        try:
            path, sha256, size = await _receive(upload, services.paths.library_incoming)
        except _RejectedUploadError as exc:
            results.append(ImportResult(file_name=name, error=str(exc)))
            continue
        document = services.library.import_file(path, name, sha256, size)
        results.append(ImportResult(file_name=name, document=document))
    return results


@router.delete(
    "/documents/{document_id}",
    operation_id="deleteDocument",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_document(document_id: str, services: Services) -> Response:
    if not await services.library.delete(document_id):
        raise DocumentNotFoundError(f"No document with id {document_id!r}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/reindex", operation_id="reindexLibrary", status_code=status.HTTP_202_ACCEPTED)
def reindex(services: Services) -> IndexStatus:
    return services.library.reindex()


@router.post("/search", operation_id="searchLibrary")
async def search(request: SearchRequest, services: Services) -> SearchResponse:
    return await services.library.search(request)

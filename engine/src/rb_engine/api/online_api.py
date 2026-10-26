"""Online discovery, its settings, and adding papers found online to the library."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from rb_engine.api.deps import Services
from rb_engine.api.library_api import ImportResult
from rb_engine.domain.errors import EngineError
from rb_engine.domain.library import DocumentMetadata
from rb_engine.domain.works import SourceName
from rb_engine.runtime.online import OPENALEX_KEY, SEMANTIC_SCHOLAR_KEY
from rb_engine.runtime.secrets import SecretStorageUnavailableError
from rb_engine.services.discovery import DiscoveryRequest, DiscoveryResponse
from rb_engine.services.pdf_download import PdfDownloadError, download_pdf

router = APIRouter(tags=["online"])


class SecureStorageUnavailableError(EngineError):
    status_code = 503
    title = "No secure storage"
    type_slug = "secure-storage-unavailable"


class OnlineSettingsView(BaseModel):
    enabled: bool
    sources: dict[SourceName, bool]
    contact_email: str | None
    has_openalex_key: bool
    has_semantic_scholar_key: bool
    secure_storage_available: bool


class OnlineSettingsUpdate(BaseModel):
    """Fields left out stay unchanged. An empty string removes a stored API key."""

    enabled: bool | None = None
    sources: dict[SourceName, bool] | None = None
    contact_email: str | None = Field(
        default=None, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    )
    clear_contact_email: bool = False
    openalex_api_key: str | None = Field(default=None, max_length=200)
    semantic_scholar_api_key: str | None = Field(default=None, max_length=200)


class ImportFromUrlRequest(BaseModel):
    url: str = Field(max_length=2000)
    metadata: DocumentMetadata | None = None


def _view(services: Services) -> OnlineSettingsView:
    online = services.online
    settings = online.settings()
    disabled = set(settings.disabled_sources)
    return OnlineSettingsView(
        enabled=settings.enabled,
        sources={name: name not in disabled for name in SourceName},
        contact_email=settings.contact_email,
        has_openalex_key=online.has_secret(OPENALEX_KEY),
        has_semantic_scholar_key=online.has_secret(SEMANTIC_SCHOLAR_KEY),
        secure_storage_available=online.secrets.available(),
    )


@router.get("/settings/online", operation_id="getOnlineSettings")
def get_online_settings(services: Services) -> OnlineSettingsView:
    return _view(services)


@router.put("/settings/online", operation_id="updateOnlineSettings")
def update_online_settings(body: OnlineSettingsUpdate, services: Services) -> OnlineSettingsView:
    online = services.online
    settings = online.settings()
    update: dict[str, object] = {}
    if body.enabled is not None:
        update["enabled"] = body.enabled
    if body.sources is not None:
        current = {name: name not in settings.disabled_sources for name in SourceName}
        current.update(body.sources)
        update["disabled_sources"] = tuple(n for n, on in current.items() if not on)
    if body.clear_contact_email:
        update["contact_email"] = None
    elif body.contact_email is not None:
        update["contact_email"] = body.contact_email
    if update:
        online.save(settings.model_copy(update=update))
    try:
        if body.openalex_api_key is not None:
            online.set_secret(OPENALEX_KEY, body.openalex_api_key)
        if body.semantic_scholar_api_key is not None:
            online.set_secret(SEMANTIC_SCHOLAR_KEY, body.semantic_scholar_api_key)
    except SecretStorageUnavailableError as exc:
        raise SecureStorageUnavailableError(
            "This system has no secure credential store, so API keys cannot be saved"
        ) from exc
    return _view(services)


@router.post("/discover", operation_id="discover")
async def discover(request: DiscoveryRequest, services: Services) -> DiscoveryResponse:
    return await services.discovery.search(request)


@router.post("/library/documents/from-url", operation_id="importDocumentFromUrl")
async def import_from_url(request: ImportFromUrlRequest, services: Services) -> ImportResult:
    name = request.url.rstrip("/").rsplit("/", 1)[-1].split("?")[0] or "document"
    file_name = name if name.lower().endswith(".pdf") else f"{name}.pdf"
    try:
        path, sha256, size = await download_pdf(request.url, services.paths.library_incoming)
    except PdfDownloadError as exc:
        return ImportResult(file_name=file_name, error=exc.detail)
    document = services.library.import_file(path, file_name, sha256, size, request.metadata)
    return ImportResult(file_name=file_name, document=document)

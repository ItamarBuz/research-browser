"""Typed error hierarchy for expected engine failures.

Each error carries the HTTP status and title it maps to, so the API edge can render an
RFC 7807 problem response without knowing about individual error types.
"""

from typing import ClassVar


class EngineError(Exception):
    """Base class for all expected (non-bug) engine failures."""

    status_code: ClassVar[int] = 500
    title: ClassVar[str] = "Engine error"
    type_slug: ClassVar[str] = "engine-error"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class SourceUnavailableError(EngineError):
    """A remote academic source could not be reached or returned an unusable response."""

    status_code = 503
    title = "Source unavailable"
    type_slug = "source-unavailable"


class ModelNotReadyError(EngineError):
    """A required local model is not downloaded, verified or loaded yet."""

    status_code = 503
    title = "Model not ready"
    type_slug = "model-not-ready"


class ModelNotFoundError(EngineError):
    """The requested model id is not in the catalog."""

    status_code = 404
    title = "Unknown model"
    type_slug = "model-not-found"


class ModelIntegrityError(EngineError):
    """A downloaded model file did not match its pinned SHA-256 hash."""

    status_code = 502
    title = "Model download corrupted"
    type_slug = "model-integrity"


class InsufficientDiskSpaceError(EngineError):
    """Not enough free disk space to download a model."""

    status_code = 507
    title = "Not enough disk space"
    type_slug = "insufficient-disk-space"


class DocumentNotFoundError(EngineError):
    status_code = 404
    title = "Unknown document"
    type_slug = "document-not-found"


class DocumentParseError(EngineError):
    """A document (e.g. an imported PDF) could not be parsed into text."""

    status_code = 422
    title = "Document could not be parsed"
    type_slug = "document-parse-error"

"""The user's local document library and search over it."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from rb_engine.text.boilerplate import PassageKind
from rb_engine.text.language import SourceLanguage

LanguageFilter = Literal["en", "he", "cross"]
"""en/he: only sources in that language; cross: any language (cross-lingual retrieval)."""


class DocumentStatus(StrEnum):
    QUEUED = "queued"
    PARSING = "parsing"
    INDEXING = "indexing"
    READY = "ready"
    """Parsed and stored. Whether it is searchable depends on the active embedding model."""
    FAILED = "failed"


class DocumentMetadata(BaseModel):
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    doi: str | None = None


class Document(BaseModel):
    id: str = Field(description="SHA-256 of the file, so the same PDF is never stored twice")
    file_name: str
    size_bytes: int
    added_at: datetime
    status: DocumentStatus
    error: str | None = None
    metadata: DocumentMetadata
    language: SourceLanguage | None = None
    page_count: int = 0
    passage_count: int = 0


class LibraryDocument(Document):
    searchable: bool = Field(description="Indexed with the active embedding model")


class IndexStatus(BaseModel):
    embedding_model: str
    model_ready: bool
    ready_documents: int
    indexed_documents: int
    pending_documents: int = Field(description="Parsed documents missing from the active index")
    busy: bool = Field(description="Documents are being imported or indexed right now")


class LibraryState(BaseModel):
    documents: list[LibraryDocument]
    index: IndexStatus


class SentenceSpan(BaseModel):
    """A sentence's position in its page's raw extracted text (for highlighting)."""

    start: int
    end: int


class Passage(BaseModel):
    id: str
    document_id: str
    index: int
    page: int = Field(description="1-based page number")
    text: str
    language: SourceLanguage
    sentences: list[SentenceSpan]
    kind: PassageKind = Field(
        default="body", description="Only body passages are indexed for search"
    )


class ParsedDocument(BaseModel):
    """Output of parsing: everything needed to store and index a document."""

    metadata: DocumentMetadata
    language: SourceLanguage
    pages: list[str]
    passages: list[Passage]


class PassageHit(BaseModel):
    passage_id: str
    page: int
    text: str
    score: float
    similarity: float = Field(description="Cosine similarity between query and passage")


class DocumentHit(BaseModel):
    document: Document
    score: float
    passages: list[PassageHit]


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    language: LanguageFilter = "cross"
    limit: int = Field(default=20, ge=1, le=100)


class SearchResponse(BaseModel):
    query_language: SourceLanguage
    embedding_model: str
    results: list[DocumentHit]
    took_ms: int

"""Scholarly works found through online academic sources."""

import re
from enum import StrEnum

from pydantic import BaseModel, Field

from rb_engine.text.language import SourceLanguage


class SourceName(StrEnum):
    OPENALEX = "openalex"
    SEMANTIC_SCHOLAR = "semantic_scholar"
    ARXIV = "arxiv"
    EUROPE_PMC = "europe_pmc"


class ExternalIds(BaseModel):
    doi: str | None = Field(default=None, description="Lowercase, without https://doi.org/")
    openalex: str | None = None
    semantic_scholar: str | None = None
    arxiv: str | None = Field(default=None, description="Without version suffix, e.g. 1706.03762")
    pmid: str | None = None
    pmcid: str | None = None


class Work(BaseModel):
    ids: ExternalIds
    title: str
    abstract: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    language: SourceLanguage | None = None
    citation_count: int | None = None
    pdf_url: str | None = Field(default=None, description="A legal open-access PDF, if known")
    landing_url: str | None = None
    sources: list[SourceName]


class SourceQuery(BaseModel):
    text: str = Field(min_length=1)
    language: SourceLanguage | None = Field(
        default=None, description="Restrict to works in this language, where the source can"
    )
    limit: int = Field(default=20, ge=1, le=100)


class SourceStatus(BaseModel):
    source: SourceName
    ok: bool
    count: int = 0
    from_cache: bool = False
    error: str | None = None


_DOI_PREFIX = re.compile(r"^(https?://(dx\.)?doi\.org/|doi:)", re.IGNORECASE)
_ARXIV_ID = re.compile(r"(\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?$", re.IGNORECASE)


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    doi = _DOI_PREFIX.sub("", value.strip()).lower()
    return doi or None


def normalize_arxiv_id(value: str | None) -> str | None:
    """'http://arxiv.org/abs/1706.03762v7' -> '1706.03762'."""
    if not value:
        return None
    match = _ARXIV_ID.search(value.strip())
    return match.group(1) if match else None

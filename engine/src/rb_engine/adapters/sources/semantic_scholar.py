"""Semantic Scholar (https://www.semanticscholar.org): papers across all fields.

Anonymous requests share one global rate limit and are often refused (HTTP 429); a free
API key (Settings) gives the app its own quota. Citation contexts for the criticism score
(M5) come from this source too.
"""

import json
from typing import Any

from rb_engine.adapters.sources.common import (
    MAX_AUTHORS,
    CredentialsProvider,
    language_of,
    parse_year,
)
from rb_engine.domain.works import (
    ExternalIds,
    SourceName,
    SourceQuery,
    Work,
    normalize_arxiv_id,
    normalize_doi,
)
from rb_engine.ports.sources import SourceHttp

URL = "https://api.semanticscholar.org/graph/v1/paper/search"
FIELDS = "title,year,abstract,externalIds,citationCount,openAccessPdf,authors,venue,url"


def parse_paper(raw: dict[str, Any]) -> Work | None:
    title = (raw.get("title") or "").strip()
    if not title:
        return None
    external = raw.get("externalIds") or {}
    abstract = (raw.get("abstract") or "").strip() or None
    pmcid = external.get("PubMedCentral")
    return Work(
        ids=ExternalIds(
            doi=normalize_doi(external.get("DOI")),
            semantic_scholar=raw.get("paperId"),
            arxiv=normalize_arxiv_id(external.get("ArXiv")),
            pmid=external.get("PubMed"),
            pmcid=f"PMC{pmcid}" if pmcid and not str(pmcid).startswith("PMC") else pmcid,
        ),
        title=title,
        abstract=abstract,
        authors=[a["name"] for a in (raw.get("authors") or [])[:MAX_AUTHORS] if a.get("name")],
        year=parse_year(raw.get("year")),
        venue=raw.get("venue") or None,
        language=language_of(None, title, abstract),
        citation_count=raw.get("citationCount"),
        pdf_url=(raw.get("openAccessPdf") or {}).get("url") or None,  # "" means none
        landing_url=raw.get("url"),
        sources=[SourceName.SEMANTIC_SCHOLAR],
    )


class SemanticScholarSource:
    name = SourceName.SEMANTIC_SCHOLAR

    def __init__(self, http: SourceHttp, credentials: CredentialsProvider) -> None:
        self._http = http
        self._credentials = credentials

    def supports_language_filter(self) -> bool:
        return False

    async def search(self, query: SourceQuery) -> tuple[list[Work], bool]:
        params: dict[str, str | int] = {"query": query.text, "limit": query.limit, "fields": FIELDS}
        key = self._credentials().semantic_scholar_api_key
        headers = {"x-api-key": key} if key else None
        fetched = await self._http.get(self.name, URL, params, headers=headers)
        papers = json.loads(fetched.body).get("data") or []
        works = [w for w in map(parse_paper, papers) if w is not None]
        return works, fetched.from_cache

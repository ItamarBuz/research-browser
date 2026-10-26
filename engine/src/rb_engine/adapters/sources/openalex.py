"""OpenAlex (https://openalex.org): ~250M scholarly works, open metadata.

Its open-access locations come from Unpaywall (both are run by OurResearch), which is how
the app finds legal free PDFs without querying Unpaywall separately.
"""

import json
from typing import Any

from rb_engine.adapters.sources.common import (
    MAX_AUTHORS,
    CredentialsProvider,
    language_of,
    parse_year,
)
from rb_engine.domain.works import ExternalIds, SourceName, SourceQuery, Work, normalize_doi
from rb_engine.ports.sources import SourceHttp

URL = "https://api.openalex.org/works"
FIELDS = (
    "id,doi,display_name,publication_year,language,cited_by_count,authorships,"
    "abstract_inverted_index,best_oa_location,primary_location,ids,type"
)


def abstract_from_inverted_index(index: dict[str, list[int]] | None) -> str | None:
    """OpenAlex ships abstracts as {word: [positions]}; rebuild the running text."""
    if not index:
        return None
    positions = {pos: word for word, places in index.items() for pos in places}
    return " ".join(positions[i] for i in sorted(positions)) or None


def _tail(url: str | None) -> str | None:
    return url.rstrip("/").rsplit("/", 1)[-1] if url else None


def parse_work(raw: dict[str, Any]) -> Work | None:
    title = (raw.get("display_name") or "").strip()
    if not title:
        return None
    abstract = abstract_from_inverted_index(raw.get("abstract_inverted_index"))
    ids = raw.get("ids") or {}
    primary = raw.get("primary_location") or {}
    best_oa = raw.get("best_oa_location") or {}
    doi = normalize_doi(raw.get("doi"))
    venue = (primary.get("source") or {}).get("display_name")
    return Work(
        ids=ExternalIds(
            doi=doi,
            openalex=_tail(raw.get("id")),
            pmid=_tail(ids.get("pmid")),
            pmcid=_tail(ids.get("pmcid")),
        ),
        title=title,
        abstract=abstract,
        authors=[
            a["author"]["display_name"]
            for a in (raw.get("authorships") or [])[:MAX_AUTHORS]
            if (a.get("author") or {}).get("display_name")
        ],
        year=parse_year(raw.get("publication_year")),
        venue=venue,
        language=language_of(raw.get("language"), title, abstract),
        citation_count=raw.get("cited_by_count"),
        pdf_url=best_oa.get("pdf_url")
        or (primary.get("pdf_url") if primary.get("is_oa") else None),
        landing_url=f"https://doi.org/{doi}" if doi else primary.get("landing_page_url"),
        sources=[SourceName.OPENALEX],
    )


class OpenAlexSource:
    name = SourceName.OPENALEX

    def __init__(self, http: SourceHttp, credentials: CredentialsProvider) -> None:
        self._http = http
        self._credentials = credentials

    def supports_language_filter(self) -> bool:
        return True

    async def search(self, query: SourceQuery) -> tuple[list[Work], bool]:
        filters = ["is_paratext:false"]
        if query.language in ("en", "he"):
            filters.append(f"language:{query.language}")
        params: dict[str, str | int] = {
            "search": query.text,
            "filter": ",".join(filters),
            "per_page": query.limit,
            "select": FIELDS,
        }
        credentials = self._credentials()
        if credentials.openalex_api_key:
            params["api_key"] = credentials.openalex_api_key
        if credentials.contact_email:
            params["mailto"] = credentials.contact_email
        fetched = await self._http.get(self.name, URL, params)
        results = json.loads(fetched.body).get("results") or []
        works = [w for w in map(parse_work, results) if w is not None]
        return works, fetched.from_cache

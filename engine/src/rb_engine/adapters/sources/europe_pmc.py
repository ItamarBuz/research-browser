"""Europe PMC (https://europepmc.org): life sciences and biomedical literature, with
abstracts, language metadata and many open-access full texts."""

import json
from typing import Any

from rb_engine.adapters.sources.common import MAX_AUTHORS, clean_text, language_of, parse_year
from rb_engine.domain.works import ExternalIds, SourceName, SourceQuery, Work, normalize_doi
from rb_engine.ports.sources import SourceHttp

URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
LANGUAGE_CODES = {"en": "eng", "he": "heb"}
OPEN_PDF_CODES = frozenset({"OA", "F"})  # open access / free to read


def _pdf_url(raw: dict[str, Any]) -> str | None:
    for link in (raw.get("fullTextUrlList") or {}).get("fullTextUrl") or []:
        if link.get("documentStyle") == "pdf" and link.get("availabilityCode") in OPEN_PDF_CODES:
            url = link.get("url")
            if isinstance(url, str):
                return url
    pmcid = raw.get("pmcid")
    if pmcid and raw.get("isOpenAccess") == "Y":
        return f"https://europepmc.org/articles/{pmcid}?pdf=render"
    return None


def _authors(raw: dict[str, Any]) -> list[str]:
    listed = (raw.get("authorList") or {}).get("author") or []
    names = [a["fullName"] for a in listed if a.get("fullName")]
    if not names and raw.get("authorString"):
        names = [n.strip() for n in str(raw["authorString"]).rstrip(".").split(",") if n.strip()]
    return names[:MAX_AUTHORS]


def parse_result(raw: dict[str, Any]) -> Work | None:
    title = clean_text(raw.get("title"))
    if not title:
        return None
    title = title.rstrip(".")
    abstract = clean_text(raw.get("abstractText"))
    doi = normalize_doi(raw.get("doi"))
    journal = ((raw.get("journalInfo") or {}).get("journal") or {}).get("title")
    try:
        citations: int | None = int(raw.get("citedByCount", ""))
    except ValueError:
        citations = None
    return Work(
        ids=ExternalIds(doi=doi, pmid=raw.get("pmid"), pmcid=raw.get("pmcid")),
        title=title,
        abstract=abstract,
        authors=_authors(raw),
        year=parse_year(raw.get("pubYear")),
        venue=journal,
        language=language_of(raw.get("language"), title, abstract),
        citation_count=citations,
        pdf_url=_pdf_url(raw),
        landing_url=(
            f"https://doi.org/{doi}"
            if doi
            else f"https://europepmc.org/article/{raw.get('source')}/{raw.get('id')}"
        ),
        sources=[SourceName.EUROPE_PMC],
    )


class EuropePmcSource:
    name = SourceName.EUROPE_PMC

    def __init__(self, http: SourceHttp) -> None:
        self._http = http

    def supports_language_filter(self) -> bool:
        return True

    async def search(self, query: SourceQuery) -> tuple[list[Work], bool]:
        text = query.text
        if query.language in LANGUAGE_CODES:
            text = f'({text}) AND LANG:"{LANGUAGE_CODES[query.language]}"'
        params: dict[str, str | int] = {
            "query": text,
            "format": "json",
            "pageSize": query.limit,
            "resultType": "core",
        }
        fetched = await self._http.get(self.name, URL, params)
        results = (json.loads(fetched.body).get("resultList") or {}).get("result") or []
        works = [w for w in map(parse_result, results) if w is not None]
        return works, fetched.from_cache

"""arXiv (https://arxiv.org): open preprints in physics, maths, CS, biology and more.

The API matches every term it is given, so long questions are reduced to their most
informative words first. Every arXiv paper has a free PDF.
"""

from xml.etree.ElementTree import Element

import defusedxml.ElementTree as SafeET

from rb_engine.adapters.sources.common import MAX_AUTHORS, clean_text, language_of, parse_year
from rb_engine.domain.works import (
    ExternalIds,
    SourceName,
    SourceQuery,
    Work,
    normalize_arxiv_id,
    normalize_doi,
)
from rb_engine.ports.sources import SourceHttp
from rb_engine.text.keywords import keywords

URL = "https://export.arxiv.org/api/query"
MAX_TERMS = 4
NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def build_query(text: str) -> str | None:
    terms = keywords(text, limit=MAX_TERMS)
    if not terms:
        return None
    return " AND ".join(f'all:"{t}"' if " " in t else f"all:{t}" for t in terms)


def _text(entry: Element, path: str) -> str | None:
    node = entry.find(path, NS)
    return clean_text(node.text) if node is not None and node.text else None


def parse_entry(entry: Element) -> Work | None:
    title = _text(entry, "a:title")
    arxiv_id = normalize_arxiv_id(_text(entry, "a:id"))
    if not title or not arxiv_id:
        return None
    abstract = _text(entry, "a:summary")
    pdf = next(
        (
            link.get("href")
            for link in entry.findall("a:link", NS)
            if link.get("title") == "pdf" or link.get("type") == "application/pdf"
        ),
        None,
    )
    return Work(
        ids=ExternalIds(arxiv=arxiv_id, doi=normalize_doi(_text(entry, "arxiv:doi"))),
        title=title,
        abstract=abstract,
        authors=[
            name
            for author in entry.findall("a:author", NS)[:MAX_AUTHORS]
            if (name := _text(author, "a:name"))
        ],
        year=parse_year(_text(entry, "a:published") or _text(entry, "a:updated")),
        venue="arXiv",
        language=language_of(None, title, abstract),
        pdf_url=pdf or f"https://arxiv.org/pdf/{arxiv_id}",
        landing_url=f"https://arxiv.org/abs/{arxiv_id}",
        sources=[SourceName.ARXIV],
    )


class ArxivSource:
    name = SourceName.ARXIV

    def __init__(self, http: SourceHttp) -> None:
        self._http = http

    def supports_language_filter(self) -> bool:
        return False

    async def search(self, query: SourceQuery) -> tuple[list[Work], bool]:
        search_query = build_query(query.text)
        if search_query is None:
            return [], False
        params: dict[str, str | int] = {
            "search_query": search_query,
            "max_results": query.limit,
            "sortBy": "relevance",
        }
        fetched = await self._http.get(self.name, URL, params)
        root = SafeET.fromstring(fetched.body)
        works = [w for w in map(parse_entry, root.findall("a:entry", NS)) if w is not None]
        return works, fetched.from_cache

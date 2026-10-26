"""Source adapters against responses recorded from the real APIs (tests/fixtures/sources)."""

from collections.abc import Mapping
from pathlib import Path

import pytest

from rb_engine.adapters.sources.arxiv import ArxivSource, build_query
from rb_engine.adapters.sources.common import SourceCredentials, clean_text
from rb_engine.adapters.sources.europe_pmc import EuropePmcSource
from rb_engine.adapters.sources.openalex import OpenAlexSource, abstract_from_inverted_index
from rb_engine.adapters.sources.semantic_scholar import SemanticScholarSource
from rb_engine.domain.works import SourceName, SourceQuery, normalize_arxiv_id, normalize_doi
from rb_engine.ports.sources import Fetched
from rb_engine.text.keywords import keyword_query, keywords

FIXTURES = Path(__file__).parent / "fixtures" / "sources"
pytestmark = pytest.mark.anyio


class RecordedHttp:
    """Replays one recorded body and remembers what the adapter asked for."""

    def __init__(self, fixture: str) -> None:
        self.body = (FIXTURES / fixture).read_text(encoding="utf-8")
        self.calls: list[tuple[str, dict[str, str | int], Mapping[str, str] | None]] = []

    async def get(
        self,
        source: SourceName,
        url: str,
        params: Mapping[str, str | int],
        *,
        headers: Mapping[str, str] | None = None,
    ) -> Fetched:
        self.calls.append((url, dict(params), headers))
        return Fetched(body=self.body, from_cache=False)


def no_credentials() -> SourceCredentials:
    return SourceCredentials()


QUERY = SourceQuery(text="sleep deprivation working memory", limit=3)


async def test_openalex_parses_works_and_rebuilds_abstracts() -> None:
    http = RecordedHttp("openalex_search.json")
    works, from_cache = await OpenAlexSource(http, no_credentials).search(
        SourceQuery(text="sleep deprivation working memory", language="en", limit=3)
    )

    assert not from_cache
    first = works[0]
    assert first.title.startswith("Sleep less, think worse")
    assert first.ids.doi == "10.1016/j.jarmac.2016.10.001"
    assert first.ids.openalex == "W2552980158"
    assert first.authors[0] == "Steven J. Frenda"
    assert first.language == "en"
    assert first.abstract is not None
    assert len(first.abstract.split()) > 50
    assert first.landing_url == "https://doi.org/10.1016/j.jarmac.2016.10.001"
    _, params, _ = http.calls[0]
    assert params["filter"] == "is_paratext:false,language:en"


async def test_openalex_sends_optional_credentials() -> None:
    http = RecordedHttp("openalex_search.json")
    creds = SourceCredentials(contact_email="me@example.org", openalex_api_key="k123")
    await OpenAlexSource(http, lambda: creds).search(QUERY)
    _, params, _ = http.calls[0]
    assert params["api_key"] == "k123"
    assert params["mailto"] == "me@example.org"


def test_abstract_from_inverted_index() -> None:
    assert abstract_from_inverted_index({"sleep": [1], "Good": [0], "matters": [2]}) == (
        "Good sleep matters"
    )
    assert abstract_from_inverted_index(None) is None


async def test_semantic_scholar_parses_and_treats_empty_pdf_as_missing() -> None:
    http = RecordedHttp("semantic_scholar_search.json")
    works, _ = await SemanticScholarSource(http, no_credentials).search(QUERY)

    first = works[0]
    assert first.ids.doi == "10.1016/j.sleep.2025.106665"
    assert first.ids.semantic_scholar == "8f30aa09f97ef5667c4cb09796e147fdf57e573b"
    assert first.pdf_url is None  # the API returns "" when there is no PDF
    assert first.authors[:2] == ["Lili Xu", "Haoyuan Zhang"]
    assert first.venue == "Sleep Medicine"


async def test_semantic_scholar_sends_api_key_header() -> None:
    http = RecordedHttp("semantic_scholar_search.json")
    creds = SourceCredentials(semantic_scholar_api_key="s2key")
    await SemanticScholarSource(http, lambda: creds).search(QUERY)
    assert http.calls[0][2] == {"x-api-key": "s2key"}


async def test_arxiv_parses_atom_entries() -> None:
    http = RecordedHttp("arxiv_search.xml")
    works, _ = await ArxivSource(http).search(QUERY)

    first = works[0]
    assert first.ids.arxiv == "2009.07233"
    assert first.title.startswith("Flexibility of brain regions during working memory")
    assert first.pdf_url is not None
    assert first.pdf_url.startswith("https://arxiv.org/pdf/2009.07233")
    assert first.landing_url == "https://arxiv.org/abs/2009.07233"
    assert first.authors
    assert first.year == 2020
    assert http.calls[0][1]["search_query"] == (
        "all:sleep AND all:deprivation AND all:working AND all:memory"
    )


async def test_europe_pmc_parses_and_strips_html() -> None:
    http = RecordedHttp("europepmc_search.json")
    works, _ = await EuropePmcSource(http).search(
        SourceQuery(text="sleep deprivation working memory", language="he", limit=3)
    )

    first = works[0]
    assert first.ids.pmcid == "PMC13333692"
    assert first.language == "en"
    assert first.abstract is not None
    assert "<h4>" not in first.abstract
    assert first.pdf_url == "https://europepmc.org/articles/PMC13333692?pdf=render"
    assert http.calls[0][1]["query"] == '(sleep deprivation working memory) AND LANG:"heb"'


def test_identifier_normalization() -> None:
    assert normalize_doi("https://doi.org/10.1000/ABC") == "10.1000/abc"
    assert normalize_doi("doi:10.1/x") == "10.1/x"
    assert normalize_arxiv_id("http://arxiv.org/abs/1706.03762v7") == "1706.03762"
    assert normalize_arxiv_id("hep-th/9901001v2") == "hep-th/9901001"


def test_clean_text_strips_markup() -> None:
    assert clean_text("<h4>Background</h4>Sleep &amp; memory") == "Background Sleep & memory"


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        (
            "Does sleep deprivation affect working memory in students?",
            ["sleep", "deprivation", "working", "memory", "students"],
        ),
        ("האם חוסר שינה משפיע על הזיכרון?", ["חוסר", "שינה", "הזיכרון"]),
        ("What is the role of BERT-based models?", ["bert-based", "models"]),
    ],
)
def test_keywords(question: str, expected: list[str]) -> None:
    assert keywords(question) == expected


def test_keyword_query_falls_back_to_text() -> None:
    assert keyword_query("what is it?") == "what is it?"
    assert build_query("how does it work?") == "all:work"

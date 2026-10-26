import pytest

from rb_engine.domain.works import SourceName
from rb_engine.services.discovery import DiscoveryRequest, DiscoveryService, merge_works
from tests.fake_embedder import FakeEmbedderResolver
from tests.fake_sources import FakeSource, FakeTranslator, work

pytestmark = pytest.mark.anyio


def service(
    sources: list[FakeSource],
    translator: FakeTranslator | None = None,
    embedders: FakeEmbedderResolver | None = None,
    library_dois: set[str] | None = None,
) -> DiscoveryService:
    return DiscoveryService(
        sources,
        translator or FakeTranslator(),
        embedders or FakeEmbedderResolver(),
        lambda: {s.name for s in sources},
        lambda: library_dois or set(),
    )


SLEEP = work("Sleep and memory in students", SourceName.OPENALEX, doi="10.1/sleep")
HEAT = work("Heat waves and wheat yields", SourceName.OPENALEX, doi="10.1/heat")


async def test_ranks_by_similarity_and_reports_sources() -> None:
    openalex = FakeSource(SourceName.OPENALEX, [HEAT, SLEEP])
    s2 = FakeSource(SourceName.SEMANTIC_SCHOLAR, [], filters=False, fail=True)

    response = await service([openalex, s2]).search(DiscoveryRequest(query="sleep and memory"))

    assert response.results[0].work.title == SLEEP.title
    assert response.results[0].similarity is not None
    statuses = {s.source: s for s in response.sources}
    assert statuses[SourceName.OPENALEX].ok
    assert statuses[SourceName.OPENALEX].count == 2
    assert not statuses[SourceName.SEMANTIC_SCHOLAR].ok
    assert statuses[SourceName.SEMANTIC_SCHOLAR].error is not None
    assert "rate limited" in statuses[SourceName.SEMANTIC_SCHOLAR].error


async def test_hebrew_question_is_translated_for_english_sources() -> None:
    openalex = FakeSource(SourceName.OPENALEX, [SLEEP])
    arxiv = FakeSource(SourceName.ARXIV, [], filters=False)
    translator = FakeTranslator()

    response = await service([openalex, arxiv], translator).search(
        DiscoveryRequest(query="האם שינה משפרת זיכרון?")
    )

    assert response.queries == {"en": "sleep and memory", "he": "האם שינה משפרת זיכרון?"}
    # arXiv gets only the English query; OpenAlex gets both, the Hebrew one filtered to he.
    assert [q.text for q in arxiv.queries] == ["sleep memory"]
    assert [(q.text, q.language) for q in openalex.queries] == [
        ("sleep memory", None),
        ("שינה משפרת זיכרון", "he"),
    ]
    assert not response.translation_missing


async def test_missing_translator_falls_back_to_the_question() -> None:
    openalex = FakeSource(SourceName.OPENALEX, [])
    response = await service([openalex], FakeTranslator(available=False)).search(
        DiscoveryRequest(query="האם שינה משפרת זיכרון?")
    )
    assert response.translation_missing
    assert response.queries["en"] == "האם שינה משפרת זיכרון?"


async def test_hebrew_filter_translates_english_question_and_skips_english_only_sources() -> None:
    hebrew_work = work("שינה וזיכרון אצל סטודנטים", SourceName.OPENALEX, lang="he")
    openalex = FakeSource(SourceName.OPENALEX, [hebrew_work, SLEEP])
    arxiv = FakeSource(SourceName.ARXIV, [SLEEP], filters=False)

    response = await service([openalex, arxiv]).search(
        DiscoveryRequest(query="sleep and memory", language="he")
    )

    assert arxiv.queries == []
    assert [h.work.title for h in response.results] == [hebrew_work.title]
    assert response.queries == {"he": "שינה וזיכרון"}


async def test_english_filter_restricts_language() -> None:
    openalex = FakeSource(SourceName.OPENALEX, [SLEEP])
    await service([openalex]).search(DiscoveryRequest(query="sleep", language="en"))
    assert openalex.queries[0].language == "en"


async def test_marks_works_already_in_the_library() -> None:
    openalex = FakeSource(SourceName.OPENALEX, [SLEEP, HEAT])
    response = await service([openalex], library_dois={"10.1/sleep"}).search(
        DiscoveryRequest(query="sleep")
    )
    marked = {h.work.ids.doi: h.in_library for h in response.results}
    assert marked == {"10.1/sleep": True, "10.1/heat": False}


async def test_without_embedder_keeps_source_order() -> None:
    openalex = FakeSource(SourceName.OPENALEX, [HEAT, SLEEP])
    response = await service([openalex], embedders=FakeEmbedderResolver(ready=False)).search(
        DiscoveryRequest(query="sleep")
    )
    assert [h.work.title for h in response.results] == [HEAT.title, SLEEP.title]
    assert response.results[0].similarity is None


def test_merge_combines_duplicates_across_sources() -> None:
    from_openalex = work("Attention Is All You Need", SourceName.OPENALEX, doi="10.5/attn")
    from_arxiv = work("Attention is all you need", SourceName.ARXIV, arxiv="1706.03762")
    from_arxiv = from_arxiv.model_copy(
        update={"pdf_url": "https://arxiv.org/pdf/1706.03762", "year": 2020}
    )
    from_s2 = work(
        "Attention Is All You Need",
        SourceName.SEMANTIC_SCHOLAR,
        doi="10.5/attn",
        arxiv="1706.03762",
    ).model_copy(update={"citation_count": 100000, "abstract": "A much longer abstract " * 5})

    merged = merge_works([[from_openalex], [from_s2], [from_arxiv]])

    assert len(merged) == 1
    combined, score = merged[0]
    assert combined.sources == [
        SourceName.OPENALEX,
        SourceName.SEMANTIC_SCHOLAR,
        SourceName.ARXIV,
    ]
    assert combined.ids.arxiv == "1706.03762"
    assert combined.citation_count == 100000
    assert combined.pdf_url == "https://arxiv.org/pdf/1706.03762"
    assert combined.abstract is not None
    assert combined.abstract.startswith("A much longer")
    assert score == pytest.approx(3 / 61)

"""Finds papers online: plans per-source queries, runs them in parallel, merges duplicates
and ranks the result by semantic similarity to the question.

Routing by the sources filter:
- en / cross: an English query (the question, or its translation from Hebrew) goes to every
  source; "en" also asks sources that can filter by language for English only.
- he, or cross with a Hebrew question: a Hebrew query goes to the sources that can filter
  by language (OpenAlex, Europe PMC); the others index almost no Hebrew.
Translation is best-effort: without the model, the original question is used.
"""

import asyncio
import logging
import re
import time
from collections.abc import Callable, Iterable, Sequence
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from rb_engine.domain.errors import EngineError, ModelNotReadyError
from rb_engine.domain.library import LanguageFilter
from rb_engine.domain.works import SourceName, SourceQuery, SourceStatus, Work
from rb_engine.ports.library import EmbedderResolver
from rb_engine.ports.sources import AcademicSource
from rb_engine.text.keywords import keyword_query
from rb_engine.text.language import SourceLanguage, detect_language

logger = logging.getLogger(__name__)

SOURCE_TIMEOUT_S = 15.0
SLOW_SOURCE_TIMEOUT_S = {SourceName.ARXIV: 25.0}
"""arXiv's API is known to take 10-20 s for some queries."""
RESULTS_PER_SOURCE = 20
RRF_K = 60
_TITLE_KEY = re.compile(r"[^\w]+")

QueryLanguage = Literal["en", "he"]


class Translator(Protocol):
    def is_available(self, source: str, target: str) -> bool: ...

    async def translate(self, text: str, source: str, target: str) -> str | None: ...


class WorkHit(BaseModel):
    work: Work
    score: float
    similarity: float | None = Field(
        description="Cosine similarity of question and title+abstract; None without a model"
    )
    in_library: bool = False


class DiscoveryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    language: LanguageFilter = "cross"
    limit: int = Field(default=20, ge=1, le=50)


class DiscoveryResponse(BaseModel):
    query_language: SourceLanguage
    queries: dict[QueryLanguage, str] = Field(description="The query text sent per language")
    translation_missing: bool = Field(
        description="A translation would have helped but the translation model is not ready"
    )
    sources: list[SourceStatus]
    results: list[WorkHit]
    took_ms: int


def _dedupe_keys(work: Work) -> list[str]:
    keys = []
    if work.ids.doi:
        keys.append(f"doi:{work.ids.doi}")
    if work.ids.arxiv:
        keys.append(f"arxiv:{work.ids.arxiv}")
    if work.ids.pmid:
        keys.append(f"pmid:{work.ids.pmid}")
    keys.append(f"title:{_TITLE_KEY.sub('', work.title.casefold())}:{work.year}")
    return keys


def _merge(a: Work, b: Work) -> Work:
    ids = a.ids.model_copy(
        update={k: v for k, v in b.ids.model_dump().items() if v and not getattr(a.ids, k)}
    )
    abstracts = [x for x in (a.abstract, b.abstract) if x]
    return a.model_copy(
        update={
            "ids": ids,
            "abstract": max(abstracts, key=len) if abstracts else None,
            "authors": a.authors if len(a.authors) >= len(b.authors) else b.authors,
            "year": a.year or b.year,
            "venue": a.venue or b.venue,
            "language": a.language or b.language,
            "citation_count": max(
                (c for c in (a.citation_count, b.citation_count) if c is not None), default=None
            ),
            "pdf_url": a.pdf_url or b.pdf_url,
            "landing_url": a.landing_url or b.landing_url,
            "sources": list(dict.fromkeys([*a.sources, *b.sources])),
        }
    )


def merge_works(ranked_lists: Iterable[Sequence[Work]]) -> list[tuple[Work, float]]:
    """Merge duplicates across sources; score each work by reciprocal rank fusion."""
    merged: list[Work] = []
    scores: list[float] = []
    index: dict[str, int] = {}
    for works in ranked_lists:
        for rank, work in enumerate(works):
            keys = _dedupe_keys(work)
            slot = next((index[k] for k in keys if k in index), None)
            if slot is None:
                slot = len(merged)
                merged.append(work)
                scores.append(0.0)
            else:
                merged[slot] = _merge(merged[slot], work)
            scores[slot] += 1.0 / (RRF_K + rank + 1)
            for key in _dedupe_keys(merged[slot]):
                index[key] = slot
    return list(zip(merged, scores, strict=True))


def _passage(work: Work) -> str:
    return f"{work.title}. {work.abstract or ''}".strip()


class DiscoveryService:
    def __init__(
        self,
        sources: Sequence[AcademicSource],
        translator: Translator,
        embedders: EmbedderResolver,
        enabled_sources: Callable[[], set[SourceName]],
        library_dois: Callable[[], set[str]],
    ) -> None:
        self._sources = sources
        self._translator = translator
        self._embedders = embedders
        self._enabled = enabled_sources
        self._library_dois = library_dois

    async def search(self, request: DiscoveryRequest) -> DiscoveryResponse:
        started = time.perf_counter()
        question = request.query.strip()
        question_language = detect_language(question)
        queries, translation_missing = await self._plan_texts(question, question_language, request)

        jobs: list[tuple[AcademicSource, SourceQuery]] = []
        enabled = self._enabled()
        for source in self._sources:
            if source.name not in enabled:
                continue
            for language, text in queries.items():
                if language == "he" and not source.supports_language_filter():
                    continue
                restrict: QueryLanguage | None = None
                if language == "he" or request.language == "en":
                    restrict = language
                jobs.append(
                    (
                        source,
                        SourceQuery(
                            text=keyword_query(text),
                            language=restrict if source.supports_language_filter() else None,
                            limit=RESULTS_PER_SOURCE,
                        ),
                    )
                )

        outcomes = await asyncio.gather(*(self._run(source, query) for source, query in jobs))
        statuses = self._statuses(jobs, outcomes, enabled)
        lists = [works for works, _, _ in outcomes]
        merged = merge_works(lists)
        if request.language != "cross":
            merged = [(w, s) for w, s in merged if w.language == request.language]

        hits = await self._rank(question, merged)
        library = self._library_dois()
        for hit in hits:
            hit.in_library = bool(hit.work.ids.doi and hit.work.ids.doi in library)
        return DiscoveryResponse(
            query_language=question_language,
            queries=queries,
            translation_missing=translation_missing,
            sources=statuses,
            results=hits[: request.limit],
            took_ms=round((time.perf_counter() - started) * 1000),
        )

    async def _plan_texts(
        self, question: str, language: SourceLanguage, request: DiscoveryRequest
    ) -> tuple[dict[QueryLanguage, str], bool]:
        queries: dict[QueryLanguage, str] = {}
        missing = False
        if request.language in ("en", "cross"):
            if language == "he":
                english = await self._translator.translate(question, "he", "en")
                missing = missing or english is None
                queries["en"] = english or question
            else:
                queries["en"] = question
        if request.language == "he" or (request.language == "cross" and language == "he"):
            if language == "he":
                queries["he"] = question
            else:
                hebrew = await self._translator.translate(question, "en", "he")
                missing = missing or hebrew is None
                if hebrew:
                    queries["he"] = hebrew
        return queries, missing

    async def _run(
        self, source: AcademicSource, query: SourceQuery
    ) -> tuple[list[Work], bool, str | None]:
        timeout = SLOW_SOURCE_TIMEOUT_S.get(source.name, SOURCE_TIMEOUT_S)
        try:
            works, from_cache = await asyncio.wait_for(source.search(query), timeout)
        except TimeoutError:
            return [], False, f"{source.name}: no answer within {timeout:.0f} s"
        except EngineError as exc:
            return [], False, exc.detail
        except Exception as exc:
            logger.exception("Source %s failed", source.name)
            return [], False, f"{source.name}: unexpected error ({exc})"
        return works, from_cache, None

    @staticmethod
    def _statuses(
        jobs: Sequence[tuple[AcademicSource, SourceQuery]],
        outcomes: Sequence[tuple[list[Work], bool, str | None]],
        enabled: set[SourceName],
    ) -> list[SourceStatus]:
        by_source: dict[SourceName, SourceStatus] = {}
        for (source, _), (works, from_cache, error) in zip(jobs, outcomes, strict=True):
            status = by_source.setdefault(source.name, SourceStatus(source=source.name, ok=False))
            if error is None:
                status.ok = True
                status.count += len(works)
                status.from_cache = status.from_cache or from_cache
            elif not status.ok:
                status.error = error
        for status in by_source.values():
            if status.ok:
                status.error = None
        return [by_source[n] for n in SourceName if n in by_source and n in enabled]

    async def _rank(self, question: str, merged: list[tuple[Work, float]]) -> list[WorkHit]:
        if not merged:
            return []
        try:
            async with self._embedders.lease() as embedder:
                query_vec = (await asyncio.to_thread(embedder.embed_queries, [question]))[0]
                vectors = await asyncio.to_thread(
                    embedder.embed_passages, [_passage(w) for w, _ in merged]
                )
        except ModelNotReadyError:
            # Without the embedding model, fall back to the sources' own ranking.
            hits = [WorkHit(work=w, score=s, similarity=None) for w, s in merged]
            return sorted(hits, key=lambda h: h.score, reverse=True)
        similarities = vectors @ query_vec
        hits = [
            WorkHit(work=w, score=float(sim), similarity=float(sim))
            for (w, _), sim in zip(merged, similarities, strict=True)
        ]
        return sorted(hits, key=lambda h: h.score, reverse=True)

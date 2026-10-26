"""Fake online sources and translator for discovery and API tests."""

from rb_engine.domain.errors import SourceUnavailableError
from rb_engine.domain.works import ExternalIds, SourceName, SourceQuery, Work


def work(title: str, source: SourceName, *, lang: str = "en", **ids: str) -> Work:
    return Work(
        ids=ExternalIds(**ids),
        title=title,
        abstract=f"An abstract about {title.lower()}.",
        authors=["A. Author"],
        year=2020,
        language=lang,  # type: ignore[arg-type]
        sources=[source],
    )


class FakeSource:
    def __init__(
        self, name: SourceName, works: list[Work], *, filters: bool = True, fail: bool = False
    ) -> None:
        self.name = name
        self.works = works
        self.filters = filters
        self.fail = fail
        self.queries: list[SourceQuery] = []

    def supports_language_filter(self) -> bool:
        return self.filters

    async def search(self, query: SourceQuery) -> tuple[list[Work], bool]:
        self.queries.append(query)
        if self.fail:
            raise SourceUnavailableError(f"{self.name}: rate limited")
        return [w for w in self.works if query.language in (None, w.language)], False


class FakeTranslator:
    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.calls: list[tuple[str, str, str]] = []

    def is_available(self, source: str, target: str) -> bool:
        return self.available

    async def translate(self, text: str, source: str, target: str) -> str | None:
        self.calls.append((text, source, target))
        if not self.available:
            return None
        return {"he": "שינה וזיכרון", "en": "sleep and memory"}[target]

"""Ports for online academic sources and the HTTP access they share."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from rb_engine.domain.works import SourceName, SourceQuery, Work


@dataclass(frozen=True, slots=True)
class Fetched:
    body: str
    from_cache: bool


class SourceHttp(Protocol):
    """Rate-limited, retrying, caching GET shared by all sources."""

    async def get(
        self,
        source: SourceName,
        url: str,
        params: Mapping[str, str | int],
        *,
        headers: Mapping[str, str] | None = None,
    ) -> Fetched: ...


class AcademicSource(Protocol):
    name: SourceName

    def supports_language_filter(self) -> bool: ...

    async def search(self, query: SourceQuery) -> tuple[list[Work], bool]:
        """Matching works, and whether the answer came from the offline cache."""
        ...


JsonObject = dict[str, Any]

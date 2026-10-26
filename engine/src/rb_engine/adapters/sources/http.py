"""Polite, resilient HTTP for academic APIs: pacing, retries and an offline cache.

Each source gets its own minimum interval between requests (arXiv asks for 3 s). 429 and
5xx answers are retried, honouring Retry-After. Successful bodies are cached in SQLite:
fresh entries answer directly, and stale ones are the fallback when the network or the
source is down, so a previous search still works offline.
"""

import asyncio
import hashlib
import json
import logging
import sqlite3
import threading
import time
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path

import httpx

from rb_engine import __version__
from rb_engine.domain.errors import SourceUnavailableError
from rb_engine.domain.works import SourceName
from rb_engine.ports.sources import Fetched

logger = logging.getLogger(__name__)

USER_AGENT = f"ResearchBrowser/{__version__} (+https://github.com/ItamarBuz/research-browser)"

MIN_INTERVAL_S: dict[SourceName, float] = {
    SourceName.OPENALEX: 0.15,
    SourceName.SEMANTIC_SCHOLAR: 1.1,
    SourceName.ARXIV: 3.0,
    SourceName.EUROPE_PMC: 0.15,
}
FRESH_FOR_S = 24 * 3600
MAX_ATTEMPTS = 2
MAX_RETRY_WAIT_S = 4.0
"""Searches are interactive: one quick retry, then fall back to cache or report the source."""
KEYED_SOURCES = frozenset({SourceName.OPENALEX, SourceName.SEMANTIC_SCHOLAR})
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
SECRET_PARAMS = frozenset({"api_key", "mailto", "email"})
"""Never part of the cache key, so keys and addresses are not written to disk."""
HTTP_TOO_MANY_REQUESTS = 429

Sleep = Callable[[float], Awaitable[None]]


class HttpCache:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS http_cache "
                "(key TEXT PRIMARY KEY, body TEXT NOT NULL, fetched_at REAL NOT NULL)"
            )

    def get(self, key: str) -> tuple[str, float] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT body, fetched_at FROM http_cache WHERE key = ?", (key,)
            ).fetchone()
        return (row[0], row[1]) if row else None

    def put(self, key: str, body: str, fetched_at: float) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO http_cache (key, body, fetched_at) VALUES (?, ?, ?)",
                (key, body, fetched_at),
            )

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def cache_key(url: str, params: Mapping[str, str | int]) -> str:
    public = {k: str(v) for k, v in sorted(params.items()) if k not in SECRET_PARAMS}
    return hashlib.sha256(json.dumps([url, public]).encode()).hexdigest()


def _retry_after(response: httpx.Response, attempt: int) -> float:
    header = response.headers.get("Retry-After", "")
    try:
        wait = float(header)
    except ValueError:
        wait = 2.0**attempt
    return min(max(wait, 0.0), MAX_RETRY_WAIT_S)


def _describe(source: SourceName, status: int) -> str:
    if status == HTTP_TOO_MANY_REQUESTS:
        hint = "; an API key in Settings raises the limit" if source in KEYED_SOURCES else ""
        return f"rate limited (too many requests){hint}"
    return f"HTTP {status}"


class CachedSourceHttp:
    def __init__(
        self,
        cache: HttpCache,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Sleep = asyncio.sleep,
        clock: Callable[[], float] = time.time,
        fresh_for_s: float = FRESH_FOR_S,
    ) -> None:
        self._cache = cache
        self._transport = transport
        self._sleep = sleep
        self._clock = clock
        self._fresh_for_s = fresh_for_s
        self._client: httpx.AsyncClient | None = None
        self._pacing: dict[SourceName, asyncio.Lock] = {}
        self._last_request: dict[SourceName, float] = {}

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                transport=self._transport,
                timeout=httpx.Timeout(20.0, connect=8.0),
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT},
            )
        return self._client

    async def get(
        self,
        source: SourceName,
        url: str,
        params: Mapping[str, str | int],
        *,
        headers: Mapping[str, str] | None = None,
    ) -> Fetched:
        key = cache_key(url, params)
        cached = self._cache.get(key)
        if cached and self._clock() - cached[1] < self._fresh_for_s:
            return Fetched(body=cached[0], from_cache=True)
        try:
            body = await self._fetch(source, url, params, headers)
        except SourceUnavailableError:
            if cached:  # stale, but better than nothing (e.g. offline)
                logger.info("%s unavailable; serving cached response", source)
                return Fetched(body=cached[0], from_cache=True)
            raise
        self._cache.put(key, body, self._clock())
        return Fetched(body=body, from_cache=False)

    async def _pace(self, source: SourceName) -> None:
        lock = self._pacing.setdefault(source, asyncio.Lock())
        async with lock:
            wait = self._last_request.get(source, 0.0) + MIN_INTERVAL_S[source] - self._clock()
            if wait > 0:
                await self._sleep(wait)
            self._last_request[source] = self._clock()

    async def _fetch(
        self,
        source: SourceName,
        url: str,
        params: Mapping[str, str | int],
        headers: Mapping[str, str] | None,
    ) -> str:
        last_problem = "no response"
        for attempt in range(1, MAX_ATTEMPTS + 1):
            await self._pace(source)
            try:
                response = await self._http().get(url, params=dict(params), headers=headers)
            except httpx.TransportError as exc:
                raise SourceUnavailableError(f"{source}: cannot connect ({exc})") from exc
            if response.status_code == httpx.codes.OK:
                return response.text
            last_problem = _describe(source, response.status_code)
            if response.status_code not in RETRY_STATUSES or attempt == MAX_ATTEMPTS:
                break
            await self._sleep(_retry_after(response, attempt))
        raise SourceUnavailableError(f"{source}: {last_problem}")

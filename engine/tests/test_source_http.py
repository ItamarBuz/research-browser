from pathlib import Path

import httpx
import pytest

from rb_engine.adapters.sources.http import CachedSourceHttp, HttpCache, cache_key
from rb_engine.domain.errors import SourceUnavailableError
from rb_engine.domain.works import SourceName

pytestmark = pytest.mark.anyio
URL = "https://api.example.org/search"


class Clock:
    def __init__(self) -> None:
        self.now = 1_000.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def make_http(tmp_path: Path, handler: httpx.MockTransport, clock: Clock) -> CachedSourceHttp:
    return CachedSourceHttp(
        HttpCache(tmp_path / "cache.sqlite3"), transport=handler, sleep=clock.sleep, clock=clock
    )


async def test_retries_rate_limits_honouring_retry_after(tmp_path: Path) -> None:
    answers = iter(
        [httpx.Response(429, headers={"Retry-After": "3"}), httpx.Response(200, text="ok")]
    )
    clock = Clock()
    http = make_http(tmp_path, httpx.MockTransport(lambda _r: next(answers)), clock)

    fetched = await http.get(SourceName.OPENALEX, URL, {"q": "x"})

    assert fetched.body == "ok"
    assert not fetched.from_cache
    assert 3.0 in clock.slept


async def test_fresh_cache_answers_without_network(tmp_path: Path) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, text="first")

    clock = Clock()
    http = make_http(tmp_path, httpx.MockTransport(handler), clock)
    await http.get(SourceName.OPENALEX, URL, {"q": "x"})
    again = await http.get(SourceName.OPENALEX, URL, {"q": "x"})

    assert again.body == "first"
    assert again.from_cache
    assert len(calls) == 1


async def test_stale_cache_is_used_when_offline(tmp_path: Path) -> None:
    online = True

    def handler(request: httpx.Request) -> httpx.Response:
        if not online:
            raise httpx.ConnectError("offline", request=request)
        return httpx.Response(200, text="cached body")

    clock = Clock()
    http = make_http(tmp_path, httpx.MockTransport(handler), clock)
    await http.get(SourceName.ARXIV, URL, {"q": "x"})
    online = False
    clock.now += 10 * 24 * 3600  # long past freshness

    fetched = await http.get(SourceName.ARXIV, URL, {"q": "x"})
    assert fetched.body == "cached body"
    assert fetched.from_cache


async def test_failure_without_cache_explains_rate_limit(tmp_path: Path) -> None:
    clock = Clock()
    http = make_http(tmp_path, httpx.MockTransport(lambda _r: httpx.Response(429)), clock)
    with pytest.raises(SourceUnavailableError, match="API key in Settings"):
        await http.get(SourceName.SEMANTIC_SCHOLAR, URL, {"q": "x"})
    # arXiv has no API keys, so it must not suggest one.
    with pytest.raises(SourceUnavailableError, match=r"rate limited \(too many requests\)$"):
        await http.get(SourceName.ARXIV, URL, {"q": "y"})


async def test_client_errors_are_not_retried(tmp_path: Path) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(400)

    clock = Clock()
    http = make_http(tmp_path, httpx.MockTransport(handler), clock)
    with pytest.raises(SourceUnavailableError, match="HTTP 400"):
        await http.get(SourceName.OPENALEX, URL, {"q": "x"})
    assert len(calls) == 1


async def test_requests_to_one_source_are_paced(tmp_path: Path) -> None:
    clock = Clock()
    http = make_http(tmp_path, httpx.MockTransport(lambda _r: httpx.Response(200, text="")), clock)
    await http.get(SourceName.ARXIV, URL, {"q": "a"})
    await http.get(SourceName.ARXIV, URL, {"q": "b"})
    assert clock.slept == [pytest.approx(3.0)]


def test_secrets_are_not_part_of_the_cache_key() -> None:
    assert cache_key(URL, {"q": "x", "api_key": "secret", "mailto": "me@x.org"}) == cache_key(
        URL, {"q": "x"}
    )
    assert cache_key(URL, {"q": "x"}) != cache_key(URL, {"q": "y"})

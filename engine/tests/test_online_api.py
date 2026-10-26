import time
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from rb_engine.runtime.container import EngineServices
from rb_engine.services import pdf_download
from tests.pdfs import SLEEP_PAPER_PAGES, make_pdf


def test_discover_returns_ranked_works_and_statuses(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.post("/discover", headers=auth_headers, json={"query": "sleep memory"})
    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["work"]["title"] == "Sleep and memory in students"
    assert body["sources"] == [
        {"source": "openalex", "ok": True, "count": 1, "from_cache": False, "error": None}
    ]


def test_online_settings_round_trip(client: TestClient, auth_headers: dict[str, str]) -> None:
    view = client.get("/settings/online", headers=auth_headers).json()
    assert view["enabled"] is True
    assert view["sources"]["arxiv"] is True
    assert view["has_openalex_key"] is False

    view = client.put(
        "/settings/online",
        headers=auth_headers,
        json={
            "sources": {"arxiv": False},
            "contact_email": "me@example.org",
            "openalex_api_key": "secret-key",
        },
    ).json()
    assert view["sources"]["arxiv"] is False
    assert view["sources"]["openalex"] is True
    assert view["contact_email"] == "me@example.org"
    assert view["has_openalex_key"] is True
    assert "secret-key" not in str(view)  # keys are write-only

    view = client.put(
        "/settings/online", headers=auth_headers, json={"openalex_api_key": ""}
    ).json()
    assert view["has_openalex_key"] is False


def test_disabling_online_search_skips_all_sources(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    client.put("/settings/online", headers=auth_headers, json={"enabled": False})
    body = client.post("/discover", headers=auth_headers, json={"query": "sleep"}).json()
    assert body["sources"] == []
    assert body["results"] == []


def test_invalid_email_is_rejected(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.put(
        "/settings/online", headers=auth_headers, json={"contact_email": "not an email"}
    )
    assert response.status_code == 422


def _serve(content: bytes, status: int = 200) -> httpx.MockTransport:
    return httpx.MockTransport(lambda _r: httpx.Response(status, content=content))


@pytest.fixture
def pdf_server(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    served: dict[str, Any] = {"transport": _serve(make_pdf(SLEEP_PAPER_PAGES))}
    original = pdf_download.download_pdf

    async def patched(url: str, incoming: Any, *, transport: Any = None) -> Any:
        return await original(url, incoming, transport=served["transport"])

    monkeypatch.setattr("rb_engine.api.online_api.download_pdf", patched)
    return served


def test_import_from_url_keeps_catalog_metadata(
    client: TestClient,
    auth_headers: dict[str, str],
    services: EngineServices,
    pdf_server: dict[str, Any],
) -> None:
    response = client.post(
        "/library/documents/from-url",
        headers=auth_headers,
        json={
            "url": "https://example.org/paper.pdf",
            "metadata": {"title": "Catalog Title", "authors": ["Ada Lovelace"], "year": 2021},
        },
    )
    assert response.status_code == 200
    assert response.json()["error"] is None

    deadline = time.monotonic() + 10
    doc: dict[str, Any] = {}
    while time.monotonic() < deadline:
        doc = client.get("/library", headers=auth_headers).json()["documents"][0]
        if doc["status"] == "ready":
            break
        time.sleep(0.05)
    assert doc["status"] == "ready"
    meta = doc["metadata"]
    assert meta["title"] == "Catalog Title"  # not the title parsed from the PDF
    assert meta["authors"] == ["Ada Lovelace"]
    assert meta["doi"] == "10.1234/jts.2021.0042"  # filled in from the PDF
    assert meta["from_catalog"] is True


def test_import_from_url_reports_html_pages(
    client: TestClient, auth_headers: dict[str, str], pdf_server: dict[str, Any]
) -> None:
    pdf_server["transport"] = _serve(b"<html>landing page</html>")
    body = client.post(
        "/library/documents/from-url",
        headers=auth_headers,
        json={"url": "https://example.org/landing"},
    ).json()
    assert body["document"] is None
    assert "web page, not a PDF" in body["error"]


def test_import_from_url_rejects_non_web_links(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    body = client.post(
        "/library/documents/from-url",
        headers=auth_headers,
        json={"url": "file:///etc/passwd"},
    ).json()
    assert "Only web" in body["error"]


def test_import_from_url_explains_publisher_blocks(
    client: TestClient, auth_headers: dict[str, str], pdf_server: dict[str, Any]
) -> None:
    pdf_server["transport"] = _serve(b"<html>Access denied</html>", status=403)
    body = client.post(
        "/library/documents/from-url",
        headers=auth_headers,
        json={"url": "https://publisher.example/paper.pdf"},
    ).json()
    assert "does not allow automatic downloads (HTTP 403)" in body["error"]
    assert "Use Open" in body["error"]

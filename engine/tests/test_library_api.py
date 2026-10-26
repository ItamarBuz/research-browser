import time
from typing import Any

from fastapi.testclient import TestClient

from tests.pdfs import CLIMATE_PAPER_PAGES, SLEEP_PAPER_PAGES, make_pdf


def _upload(client: TestClient, headers: dict[str, str], *files: tuple[str, bytes]) -> Any:
    response = client.post(
        "/library/documents",
        headers=headers,
        files=[("files", (name, content, "application/pdf")) for name, content in files],
    )
    assert response.status_code == 200, response.text
    return response.json()


def _wait_until_idle(client: TestClient, headers: dict[str, str]) -> Any:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        state = client.get("/library", headers=headers).json()
        settled = all(d["status"] in ("ready", "failed") for d in state["documents"])
        if settled and not state["index"]["busy"]:
            return state
        time.sleep(0.05)
    raise AssertionError("library did not settle")


def test_import_search_and_delete(client: TestClient, auth_headers: dict[str, str]) -> None:
    results = _upload(
        client,
        auth_headers,
        ("sleep.pdf", make_pdf(SLEEP_PAPER_PAGES)),
        ("climate.pdf", make_pdf(CLIMATE_PAPER_PAGES)),
        ("notes.txt", b"just some text"),
    )
    assert [r["error"] for r in results] == [None, None, "Not a PDF file"]
    sleep_id = results[0]["document"]["id"]

    state = _wait_until_idle(client, auth_headers)
    assert {d["status"] for d in state["documents"]} == {"ready"}
    assert all(d["searchable"] for d in state["documents"])
    assert state["index"]["indexed_documents"] == 2

    response = client.post(
        "/library/search", headers=auth_headers, json={"query": "sleep and memory"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["document"]["id"] == sleep_id
    assert body["results"][0]["passages"][0]["page"] >= 1

    assert client.delete(f"/library/documents/{sleep_id}", headers=auth_headers).status_code == 204
    missing = client.delete(f"/library/documents/{sleep_id}", headers=auth_headers)
    assert missing.status_code == 404
    assert missing.json()["type"] == "urn:rb-engine:problem:document-not-found"


def test_search_validates_input(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/library/search", headers=auth_headers, json={"query": "", "language": "fr"}
    )
    assert response.status_code == 422


def test_reindex_reports_status(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post("/library/reindex", headers=auth_headers)
    assert response.status_code == 202
    assert response.json()["embedding_model"] == "embed-test"


def test_empty_upload_is_rejected(client: TestClient, auth_headers: dict[str, str]) -> None:
    (result,) = _upload(client, auth_headers, ("empty.pdf", b""))
    assert result["error"] == "The file is empty"

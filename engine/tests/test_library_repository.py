import sqlite3
from pathlib import Path

from rb_engine.adapters.store.library_repository import SCHEMA_VERSION, LibraryRepository
from rb_engine.domain.library import (
    Document,
    DocumentMetadata,
    DocumentStatus,
    ParsedDocument,
    Passage,
)

SCHEMA_V1 = """
CREATE TABLE documents (
    id TEXT PRIMARY KEY, file_name TEXT NOT NULL, size_bytes INTEGER NOT NULL,
    added_at TEXT NOT NULL, status TEXT NOT NULL, error TEXT, metadata TEXT NOT NULL,
    language TEXT, page_count INTEGER NOT NULL DEFAULT 0, passage_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE pages (
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page INTEGER NOT NULL, text TEXT NOT NULL, PRIMARY KEY (document_id, page)
);
CREATE TABLE passages (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL, page INTEGER NOT NULL, text TEXT NOT NULL, language TEXT NOT NULL,
    sentences TEXT NOT NULL
);
CREATE INDEX passages_by_document ON passages (document_id, idx);
PRAGMA user_version = 1;
"""


def _document(doc_id: str, status: DocumentStatus) -> Document:
    return Document(
        id=doc_id,
        file_name=f"{doc_id}.pdf",
        size_bytes=1,
        added_at="2026-10-25T00:00:00Z",
        status=status,
        metadata=DocumentMetadata(title=doc_id),
    )


def _passage(doc_id: str, index: int, kind: str) -> Passage:
    return Passage.model_validate(
        {
            "id": f"{doc_id}:{index}",
            "document_id": doc_id,
            "index": index,
            "page": 1,
            "text": f"text {index}",
            "language": "en",
            "sentences": [{"start": 0, "end": 6}],
            "kind": kind,
        }
    )


def test_passage_kinds_are_stored(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "library.sqlite3")
    repo.add_document(_document("a", DocumentStatus.PARSING))
    passages = [_passage("a", 0, "body"), _passage("a", 1, "references")]
    parsed = ParsedDocument(
        metadata=DocumentMetadata(title="A"), language="en", pages=["p1"], passages=passages
    )

    repo.save_parsed("a", parsed)

    assert repo.passages_for_document("a") == passages
    assert repo.passages_by_ids(["a:1"])["a:1"].kind == "references"
    document = repo.get_document("a")
    assert document is not None
    assert document.passage_count == 2
    repo.close()


def test_upgrading_from_v1_keeps_passages_and_queues_documents_for_reparsing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "library.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA_V1)
    for doc_id, status in (("ready", "ready"), ("indexing", "indexing"), ("failed", "failed")):
        conn.execute(
            "INSERT INTO documents (id, file_name, size_bytes, added_at, status, metadata) "
            "VALUES (?, 'x.pdf', 1, '2026-10-25T00:00:00+00:00', ?, '{\"title\": \"x\"}')",
            (doc_id, status),
        )
    conn.execute(
        "INSERT INTO passages VALUES ('ready:0', 'ready', 0, 1, 'old text', 'en', '[[0, 8]]')"
    )
    conn.commit()
    conn.close()

    repo = LibraryRepository(path)

    (passage,) = repo.passages_for_document("ready")
    assert (passage.text, passage.kind) == ("old text", "body")
    statuses = {d.id: d.status for d in repo.list_documents()}
    assert statuses == {
        "ready": DocumentStatus.QUEUED,
        "indexing": DocumentStatus.QUEUED,
        "failed": DocumentStatus.FAILED,
    }
    repo.close()
    with sqlite3.connect(path) as check:
        assert check.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_reopening_a_current_database_changes_nothing(tmp_path: Path) -> None:
    path = tmp_path / "library.sqlite3"
    repo = LibraryRepository(path)
    repo.add_document(_document("a", DocumentStatus.READY))
    repo.close()

    reopened = LibraryRepository(path)
    document = reopened.get_document("a")
    assert document is not None
    assert document.status == DocumentStatus.READY
    reopened.close()

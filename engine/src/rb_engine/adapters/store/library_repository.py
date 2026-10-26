"""SQLite store for library documents, their page text and passages.

This is the source of truth; search indexes are derived from it and can be rebuilt.
"""

import json
import sqlite3
import threading
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from rb_engine.domain.library import (
    Document,
    DocumentMetadata,
    DocumentStatus,
    ParsedDocument,
    Passage,
    SentenceSpan,
)

SCHEMA_VERSION = 1
SCHEMA = """
CREATE TABLE documents (
    id TEXT PRIMARY KEY,
    file_name TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    added_at TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    metadata TEXT NOT NULL,
    language TEXT,
    page_count INTEGER NOT NULL DEFAULT 0,
    passage_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE pages (
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page INTEGER NOT NULL,
    text TEXT NOT NULL,
    PRIMARY KEY (document_id, page)
);
CREATE TABLE passages (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    page INTEGER NOT NULL,
    text TEXT NOT NULL,
    language TEXT NOT NULL,
    sentences TEXT NOT NULL
);
CREATE INDEX passages_by_document ON passages (document_id, idx);
"""

_DOCUMENT_COLUMNS = (
    "id, file_name, size_bytes, added_at, status, error, metadata, language, page_count, "
    "passage_count"
)


def _document_from_row(row: sqlite3.Row) -> Document:
    return Document(
        id=row["id"],
        file_name=row["file_name"],
        size_bytes=row["size_bytes"],
        added_at=datetime.fromisoformat(row["added_at"]),
        status=DocumentStatus(row["status"]),
        error=row["error"],
        metadata=DocumentMetadata.model_validate_json(row["metadata"]),
        language=row["language"],
        page_count=row["page_count"],
        passage_count=row["passage_count"],
    )


def _passage_from_row(row: sqlite3.Row) -> Passage:
    return Passage(
        id=row["id"],
        document_id=row["document_id"],
        index=row["idx"],
        page=row["page"],
        text=row["text"],
        language=row["language"],
        sentences=[SentenceSpan(start=s, end=e) for s, e in json.loads(row["sentences"])],
    )


class LibraryRepository:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        # One connection shared by the event loop and worker threads, serialized by a lock.
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.execute("PRAGMA foreign_keys = ON")
            version = self._conn.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                # executescript() commits implicitly, so the transaction lives in the script.
                self._conn.executescript(
                    f"BEGIN;\n{SCHEMA}\nPRAGMA user_version = {SCHEMA_VERSION};\nCOMMIT;"
                )

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                yield self._conn
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            self._conn.execute("COMMIT")

    # --- documents -----------------------------------------------------------------------

    def add_document(self, document: Document) -> None:
        with self._transaction() as conn:
            conn.execute(
                f"INSERT INTO documents ({_DOCUMENT_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    document.id,
                    document.file_name,
                    document.size_bytes,
                    document.added_at.isoformat(),
                    document.status,
                    document.error,
                    document.metadata.model_dump_json(),
                    document.language,
                    document.page_count,
                    document.passage_count,
                ),
            )

    def get_document(self, document_id: str) -> Document | None:
        with self._lock:
            row = self._conn.execute(
                f"SELECT {_DOCUMENT_COLUMNS} FROM documents WHERE id = ?", (document_id,)
            ).fetchone()
        return _document_from_row(row) if row else None

    def list_documents(self) -> list[Document]:
        with self._lock:
            rows = self._conn.execute(
                f"SELECT {_DOCUMENT_COLUMNS} FROM documents ORDER BY added_at DESC"
            ).fetchall()
        return [_document_from_row(row) for row in rows]

    def documents_by_ids(self, ids: Iterable[str]) -> dict[str, Document]:
        id_list = list(set(ids))
        if not id_list:
            return {}
        marks = ",".join("?" * len(id_list))
        with self._lock:
            rows = self._conn.execute(
                f"SELECT {_DOCUMENT_COLUMNS} FROM documents WHERE id IN ({marks})", id_list
            ).fetchall()
        return {row["id"]: _document_from_row(row) for row in rows}

    def set_status(
        self, document_id: str, status: DocumentStatus, error: str | None = None
    ) -> None:
        with self._transaction() as conn:
            conn.execute(
                "UPDATE documents SET status = ?, error = ? WHERE id = ?",
                (status, error, document_id),
            )

    def delete_document(self, document_id: str) -> bool:
        with self._transaction() as conn:
            cursor = conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
        return cursor.rowcount > 0

    # --- content -------------------------------------------------------------------------

    def save_parsed(self, document_id: str, parsed: ParsedDocument) -> None:
        with self._transaction() as conn:
            conn.execute("DELETE FROM pages WHERE document_id = ?", (document_id,))
            conn.execute("DELETE FROM passages WHERE document_id = ?", (document_id,))
            conn.executemany(
                "INSERT INTO pages (document_id, page, text) VALUES (?, ?, ?)",
                [(document_id, n, text) for n, text in enumerate(parsed.pages, start=1)],
            )
            conn.executemany(
                "INSERT INTO passages (id, document_id, idx, page, text, language, sentences) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        p.id,
                        document_id,
                        p.index,
                        p.page,
                        p.text,
                        p.language,
                        json.dumps([[s.start, s.end] for s in p.sentences]),
                    )
                    for p in parsed.passages
                ],
            )
            conn.execute(
                "UPDATE documents SET metadata = ?, language = ?, page_count = ?, "
                "passage_count = ? WHERE id = ?",
                (
                    parsed.metadata.model_dump_json(),
                    parsed.language,
                    len(parsed.pages),
                    len(parsed.passages),
                    document_id,
                ),
            )

    def passages_for_document(self, document_id: str) -> list[Passage]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM passages WHERE document_id = ? ORDER BY idx", (document_id,)
            ).fetchall()
        return [_passage_from_row(row) for row in rows]

    def passages_by_ids(self, ids: Iterable[str]) -> dict[str, Passage]:
        id_list = list(set(ids))
        if not id_list:
            return {}
        marks = ",".join("?" * len(id_list))
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM passages WHERE id IN ({marks})", id_list
            ).fetchall()
        return {row["id"]: _passage_from_row(row) for row in rows}

    def page_text(self, document_id: str, page: int) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT text FROM pages WHERE document_id = ? AND page = ?", (document_id, page)
            ).fetchone()
        return row["text"] if row else None

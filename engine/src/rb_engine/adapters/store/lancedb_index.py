"""Hybrid passage index on LanceDB: dense vectors + BM25 full-text, fused with RRF.

One table per embedding model (`passages__<model id>`), because vectors from different
models are not comparable. Switching tiers therefore means filling a new table, while the
old one stays on disk for switching back.
"""

import logging
import re
import threading
from collections.abc import Sequence
from pathlib import Path

import lancedb
import numpy as np
import numpy.typing as npt
import pyarrow as pa
from lancedb.index import FTS
from lancedb.rerankers import RRFReranker

from rb_engine.ports.library import IndexedPassage, IndexHit
from rb_engine.text.language import SourceLanguage

logger = logging.getLogger(__name__)

TEXT_COLUMN = "search_text"
_SAFE_ID = re.compile(r"^[A-Za-z0-9:_-]+$")


def table_name(model_id: str) -> str:
    return "passages__" + re.sub(r"[^A-Za-z0-9_]", "_", model_id)


def _schema(dimension: int) -> pa.Schema:
    return pa.schema(
        [
            pa.field("passage_id", pa.string(), nullable=False),
            pa.field("document_id", pa.string(), nullable=False),
            pa.field("language", pa.string(), nullable=False),
            pa.field(TEXT_COLUMN, pa.string(), nullable=False),
            pa.field("vector", pa.list_(pa.float32(), dimension), nullable=False),
        ]
    )


def _quote(value: str) -> str:
    # Ids are hex hashes or "<hash>:<n>"; reject anything else rather than escaping SQL.
    if not _SAFE_ID.match(value):
        raise ValueError(f"unsafe id {value!r}")
    return f"'{value}'"


class LanceIndexStore:
    """Opens (and caches) one LancePassageIndex per embedding model."""

    def __init__(self, db_dir: Path) -> None:
        db_dir.mkdir(parents=True, exist_ok=True)
        self._db = lancedb.connect(db_dir)
        self._open: dict[str, LancePassageIndex] = {}
        self._lock = threading.Lock()

    def open(self, model_id: str, dimension: int | None = None) -> "LancePassageIndex | None":
        with self._lock:
            if model_id in self._open:
                return self._open[model_id]
            name = table_name(model_id)
            if name in self._db.list_tables().tables:
                table = self._db.open_table(name)
            elif dimension is not None:
                table = self._db.create_table(name, schema=_schema(dimension))
            else:
                return None
            index = LancePassageIndex(table)
            self._open[model_id] = index
            return index


class LancePassageIndex:
    def __init__(self, table: lancedb.table.Table) -> None:
        self._table = table
        self._lock = threading.Lock()
        self._has_fts = any(TEXT_COLUMN in i.columns for i in self._table.list_indices())

    def add(self, passages: Sequence[IndexedPassage]) -> None:
        if not passages:
            return
        rows = [
            {
                "passage_id": p.passage_id,
                "document_id": p.document_id,
                "language": p.language,
                TEXT_COLUMN: p.search_text,
                "vector": p.vector.astype(np.float32).tolist(),
            }
            for p in passages
        ]
        with self._lock:
            self._table.add(rows)
            if not self._has_fts:
                # English stemming helps English terms and leaves Hebrew tokens untouched;
                # Hebrew prefixes are handled by the search form itself.
                self._table.create_index(
                    TEXT_COLUMN, config=FTS(stem=True, remove_stop_words=False, ascii_folding=True)
                )
                self._has_fts = True
            else:
                self._table.optimize()  # folds new rows into the FTS index and compacts

    def delete_document(self, document_id: str) -> None:
        with self._lock:
            self._table.delete(f"document_id = {_quote(document_id)}")

    def document_ids(self) -> set[str]:
        with self._lock:
            column = self._table.to_arrow().column("document_id")
        return {str(v) for v in column.unique().to_pylist()}

    def search(
        self,
        vector: npt.NDArray[np.float32],
        text: str,
        language: SourceLanguage | None,
        limit: int,
    ) -> list[IndexHit]:
        with self._lock:
            if self._table.count_rows() == 0:
                return []
            where = f"language = '{language}'" if language else None
            if text.strip() and self._has_fts:
                query = (
                    self._table.search(query_type="hybrid")
                    .vector(vector.tolist())
                    .text(text)
                    .distance_type("cosine")  # type: ignore[attr-defined]  # typed as base builder
                    .rerank(RRFReranker())
                )
            else:
                query = self._table.search(vector.tolist()).distance_type("cosine")  # type: ignore[attr-defined]
            if where:
                query = query.where(where, prefilter=True)
            rows = query.limit(limit).to_list()

        hits: list[IndexHit] = []
        for row in rows:
            similarity = float(np.dot(np.asarray(row["vector"], dtype=np.float32), vector))
            score = row.get("_relevance_score")
            hits.append(
                IndexHit(
                    passage_id=row["passage_id"],
                    document_id=row["document_id"],
                    score=float(score) if score is not None else similarity,
                    similarity=similarity,
                )
            )
        return hits

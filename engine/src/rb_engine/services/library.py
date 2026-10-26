"""The local document library: import, parse, index, search and delete.

Imports are processed one at a time by a background worker, so a large batch never
competes with itself for memory. Parsing does not need any model; indexing needs the active
embedding model, and documents parsed while it is missing simply wait until "index now".
"""

import asyncio
import contextlib
import logging
import shutil
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from rb_engine.adapters.store.library_repository import LibraryRepository
from rb_engine.domain.errors import EngineError
from rb_engine.domain.library import (
    Document,
    DocumentHit,
    DocumentMetadata,
    DocumentStatus,
    IndexStatus,
    LibraryDocument,
    LibraryState,
    Passage,
    PassageHit,
    SearchRequest,
    SearchResponse,
)
from rb_engine.ports.library import (
    EmbedderResolver,
    IndexedPassage,
    IndexHit,
    PassageIndex,
    PassageIndexStore,
    PdfParser,
)
from rb_engine.services.document_parser import parse_document
from rb_engine.text.language import detect_language
from rb_engine.text.search_form import search_form

logger = logging.getLogger(__name__)

PASSAGES_PER_RESULT = 3
CANDIDATES_PER_RESULT = 5
"""Passages fetched per requested document, so several documents can fill the result list."""

PASSAGE_SIMILARITY_MARGIN = 0.04
"""Within a document, show only passages nearly as similar as its best one. Interim
heuristic tuned on multilingual E5 (whose similarities are tightly bunched); M4's reranker
and calibrated match % replace it."""

JobKind = Literal["process", "index"]


def group_hits(
    hits: Sequence[IndexHit],
    documents: Mapping[str, Document],
    passages: Mapping[str, Passage],
) -> list[DocumentHit]:
    """Group passage hits by document (best fused score first), keeping each document's
    most relevant passages."""
    results: dict[str, DocumentHit] = {}
    for hit in sorted(hits, key=lambda h: h.score, reverse=True):
        document, passage = documents.get(hit.document_id), passages.get(hit.passage_id)
        if document is None or passage is None:
            continue  # deleted since it was indexed
        result = results.setdefault(
            document.id, DocumentHit(document=document, score=hit.score, passages=[])
        )
        result.passages.append(
            PassageHit(
                passage_id=passage.id,
                page=passage.page,
                text=passage.text,
                score=hit.score,
                similarity=hit.similarity,
            )
        )
    for result in results.values():
        best = max(p.similarity for p in result.passages)
        result.passages = [
            p for p in result.passages if p.similarity >= best - PASSAGE_SIMILARITY_MARGIN
        ][:PASSAGES_PER_RESULT]
    return list(results.values())


class LibraryService:
    def __init__(
        self,
        repository: LibraryRepository,
        files_dir: Path,
        parser: PdfParser,
        embedders: EmbedderResolver,
        indexes: PassageIndexStore,
    ) -> None:
        self._repo = repository
        self._files_dir = files_dir
        self._parser = parser
        self._embedders = embedders
        self._indexes = indexes
        self._queue: asyncio.Queue[tuple[JobKind, str]] = asyncio.Queue()
        self._pending: set[tuple[JobKind, str]] = set()
        self._worker: asyncio.Task[None] | None = None
        self._active_jobs = 0

    # --- lifecycle -----------------------------------------------------------------------

    async def start(self) -> None:
        # Documents interrupted by a crash or shutdown are picked up again.
        for doc in self._repo.list_documents():
            if doc.status in (DocumentStatus.QUEUED, DocumentStatus.PARSING):
                self._enqueue("process", doc.id)
            elif doc.status == DocumentStatus.INDEXING:
                self._repo.set_status(doc.id, DocumentStatus.READY)
        self._worker = asyncio.create_task(self._run(), name="library-worker")

    async def stop(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker
            self._worker = None

    async def wait_idle(self) -> None:
        """Wait until every queued job has finished (used by tests)."""
        await self._queue.join()

    # --- commands ------------------------------------------------------------------------

    def import_file(self, temp_path: Path, file_name: str, sha256: str, size: int) -> Document:
        """Take ownership of an uploaded file and queue it for processing."""
        existing = self._repo.get_document(sha256)
        if existing is not None:
            temp_path.unlink(missing_ok=True)
            if existing.status == DocumentStatus.FAILED:
                self._repo.set_status(existing.id, DocumentStatus.QUEUED)
                self._enqueue("process", existing.id)
                return self._repo.get_document(sha256) or existing
            return existing

        self._files_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(temp_path, self._file_path(sha256))
        document = Document(
            id=sha256,
            file_name=file_name,
            size_bytes=size,
            added_at=datetime.now(UTC),
            status=DocumentStatus.QUEUED,
            metadata=DocumentMetadata(title=Path(file_name).stem),
        )
        self._repo.add_document(document)
        self._enqueue("process", sha256)
        return document

    def reindex(self) -> IndexStatus:
        """Queue every parsed document that is missing from the active model's index."""
        indexed = self._indexed_ids()
        for doc in self._repo.list_documents():
            if doc.status == DocumentStatus.READY and doc.id not in indexed:
                self._enqueue("index", doc.id)
        return self.index_status()

    async def delete(self, document_id: str) -> bool:
        removed = self._repo.delete_document(document_id)
        for model_id in self._embedders.known_model_ids():
            index = self._indexes.open(model_id)
            if index is not None:
                await asyncio.to_thread(index.delete_document, document_id)
        self._file_path(document_id).unlink(missing_ok=True)
        return removed

    # --- queries -------------------------------------------------------------------------

    def state(self) -> LibraryState:
        indexed = self._indexed_ids()
        documents = [
            LibraryDocument(**doc.model_dump(), searchable=doc.id in indexed)
            for doc in self._repo.list_documents()
        ]
        return LibraryState(documents=documents, index=self.index_status(indexed))

    def index_status(self, indexed: set[str] | None = None) -> IndexStatus:
        indexed = self._indexed_ids() if indexed is None else indexed
        ready = {d.id for d in self._repo.list_documents() if d.status == DocumentStatus.READY}
        return IndexStatus(
            embedding_model=self._embedders.active_model_id(),
            model_ready=self._embedders.is_ready(),
            ready_documents=len(ready),
            indexed_documents=len(ready & indexed),
            pending_documents=len(ready - indexed),
            busy=self._active_jobs > 0 or not self._queue.empty(),
        )

    async def search(self, request: SearchRequest) -> SearchResponse:
        started = time.perf_counter()
        model_id = self._embedders.active_model_id()
        async with self._embedders.lease() as embedder:
            vectors = await asyncio.to_thread(embedder.embed_queries, [request.query])
        query_language = detect_language(request.query)

        index = self._indexes.open(model_id)
        hits = []
        if index is not None:
            language = None if request.language == "cross" else request.language
            hits = await asyncio.to_thread(
                index.search,
                vectors[0],
                search_form(request.query),
                language,
                request.limit * CANDIDATES_PER_RESULT,
            )

        documents = self._repo.documents_by_ids(h.document_id for h in hits)
        passages = self._repo.passages_by_ids(h.passage_id for h in hits)
        return SearchResponse(
            query_language=query_language,
            embedding_model=model_id,
            results=group_hits(hits, documents, passages)[: request.limit],
            took_ms=round((time.perf_counter() - started) * 1000),
        )

    # --- worker --------------------------------------------------------------------------

    def _file_path(self, document_id: str) -> Path:
        return self._files_dir / f"{document_id}.pdf"

    def _writable_index(self, model_id: str, dimension: int) -> PassageIndex:
        index = self._indexes.open(model_id, dimension)
        if index is None:  # open() creates the index when given a dimension
            raise RuntimeError(f"could not create the index for {model_id}")
        return index

    def _indexed_ids(self) -> set[str]:
        index = self._indexes.open(self._embedders.active_model_id())
        return index.document_ids() if index is not None else set()

    def _enqueue(self, kind: JobKind, document_id: str) -> None:
        job = (kind, document_id)
        if job not in self._pending:
            self._pending.add(job)
            self._queue.put_nowait(job)

    async def _run(self) -> None:
        while True:
            job = await self._queue.get()
            self._pending.discard(job)
            self._active_jobs += 1
            try:
                kind, document_id = job
                if kind == "process":
                    await self._process(document_id)
                else:
                    await self._index(document_id)
            except Exception:
                logger.exception("Library job %s failed", job)
            finally:
                self._active_jobs -= 1
                self._queue.task_done()

    async def _process(self, document_id: str) -> None:
        document = self._repo.get_document(document_id)
        if document is None:
            return
        self._repo.set_status(document_id, DocumentStatus.PARSING)
        try:
            raw = await asyncio.to_thread(self._parser.extract, self._file_path(document_id))
            parsed = await asyncio.to_thread(parse_document, raw, document_id, document.file_name)
        except EngineError as exc:
            self._repo.set_status(document_id, DocumentStatus.FAILED, exc.detail)
            return
        except Exception as exc:
            logger.exception("Parsing %s failed", document_id)
            self._repo.set_status(document_id, DocumentStatus.FAILED, f"Unexpected error: {exc}")
            return
        self._repo.save_parsed(document_id, parsed)
        self._repo.set_status(document_id, DocumentStatus.READY)
        if self._embedders.is_ready():
            await self._index(document_id)

    async def _index(self, document_id: str) -> None:
        document = self._repo.get_document(document_id)
        if document is None or document.status != DocumentStatus.READY:
            return
        passages = self._repo.passages_for_document(document_id)
        model_id = self._embedders.active_model_id()
        self._repo.set_status(document_id, DocumentStatus.INDEXING)
        try:
            async with self._embedders.lease() as embedder:
                vectors = await asyncio.to_thread(
                    embedder.embed_passages, [p.text for p in passages]
                )
                dimension = embedder.dimension
            index = self._writable_index(model_id, dimension)
            rows = [
                IndexedPassage(
                    passage_id=p.id,
                    document_id=document_id,
                    language=document.language or "other",
                    search_text=search_form(p.text),
                    vector=vectors[i],
                )
                for i, p in enumerate(passages)
            ]
            await asyncio.to_thread(index.delete_document, document_id)  # idempotent re-index
            await asyncio.to_thread(index.add, rows)
        except EngineError as exc:
            self._repo.set_status(document_id, DocumentStatus.READY, exc.detail)
            return
        except Exception as exc:
            logger.exception("Indexing %s failed", document_id)
            self._repo.set_status(document_id, DocumentStatus.READY, f"Indexing failed: {exc}")
            return
        self._repo.set_status(document_id, DocumentStatus.READY)

import hashlib
import textwrap
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from rb_engine.adapters.pdf.pdfium_parser import PdfiumParser
from rb_engine.adapters.store.lancedb_index import LanceIndexStore
from rb_engine.adapters.store.library_repository import LibraryRepository
from rb_engine.domain.errors import ModelNotReadyError
from rb_engine.domain.library import (
    Document,
    DocumentMetadata,
    DocumentStatus,
    Passage,
    SearchRequest,
)
from rb_engine.ports.library import IndexHit
from rb_engine.services.library import LibraryService, group_hits, searchable_passages
from rb_engine.text.search_form import search_form
from tests.boilerplate_samples import LIGO_REFERENCES
from tests.fake_embedder import FakeEmbedder, FakeEmbedderResolver
from tests.pdfs import CLIMATE_PAPER_PAGES, SLEEP_PAPER_PAGES, make_pdf

pytestmark = pytest.mark.anyio

SLEEP_PDF = make_pdf(SLEEP_PAPER_PAGES)
CLIMATE_PDF = make_pdf(CLIMATE_PAPER_PAGES)
PAPER_WITH_REFERENCES_PDF = make_pdf(
    [*SLEEP_PAPER_PAGES, ["References", *textwrap.wrap(LIGO_REFERENCES, 90)]]
)


class Harness:
    def __init__(self, root: Path, embedders: FakeEmbedderResolver) -> None:
        self.root = root
        self.embedders = embedders
        self.service = self._new_service()

    def _new_service(self) -> LibraryService:
        return LibraryService(
            LibraryRepository(self.root / "library.sqlite3"),
            self.root / "files",
            PdfiumParser(),
            self.embedders,
            LanceIndexStore(self.root / "index"),
        )

    def import_bytes(self, content: bytes, name: str) -> str:
        temp = self.root / f"upload-{name}"
        temp.write_bytes(content)
        sha = hashlib.sha256(content).hexdigest()
        self.service.import_file(temp, name, sha, len(content))
        return sha

    async def settle(self) -> None:
        await self.service.wait_idle()

    def status(self, doc_id: str) -> DocumentStatus:
        return next(d.status for d in self.service.state().documents if d.id == doc_id)


@pytest.fixture
async def lib(tmp_path: Path) -> AsyncIterator[Harness]:
    harness = Harness(tmp_path, FakeEmbedderResolver())
    await harness.service.start()
    yield harness
    await harness.service.stop()


async def test_imports_parses_and_indexes(lib: Harness) -> None:
    doc_id = lib.import_bytes(SLEEP_PDF, "sleep.pdf")
    await lib.settle()

    (doc,) = lib.service.state().documents
    assert doc.id == doc_id
    assert doc.status == DocumentStatus.READY
    assert doc.searchable
    assert doc.metadata.title == "Sleep and Memory Consolidation in Adults"
    assert doc.language == "en"
    assert doc.page_count == 3
    assert (lib.root / "files" / f"{doc_id}.pdf").read_bytes() == SLEEP_PDF


async def test_search_ranks_the_relevant_document_first(lib: Harness) -> None:
    sleep_id = lib.import_bytes(SLEEP_PDF, "sleep.pdf")
    climate_id = lib.import_bytes(CLIMATE_PDF, "climate.pdf")
    await lib.settle()

    response = await lib.service.search(SearchRequest(query="does sleep help memory"))
    assert response.results[0].document.id == sleep_id
    assert "sleep" in response.results[0].passages[0].text.lower()
    assert response.query_language == "en"

    response = await lib.service.search(SearchRequest(query="wheat yields heat waves"))
    assert response.results[0].document.id == climate_id


async def test_language_filter_excludes_other_languages(lib: Harness) -> None:
    lib.import_bytes(SLEEP_PDF, "sleep.pdf")
    await lib.settle()

    hebrew_only = await lib.service.search(SearchRequest(query="sleep memory", language="he"))
    english_only = await lib.service.search(SearchRequest(query="sleep memory", language="en"))
    assert hebrew_only.results == []
    assert len(english_only.results) == 1


async def test_duplicate_import_is_ignored(lib: Harness) -> None:
    lib.import_bytes(SLEEP_PDF, "sleep.pdf")
    lib.import_bytes(SLEEP_PDF, "copy of sleep.pdf")
    await lib.settle()
    assert len(lib.service.state().documents) == 1


async def test_unparseable_pdf_fails_with_reason(lib: Harness) -> None:
    doc_id = lib.import_bytes(b"%PDF-1.4 truncated garbage", "broken.pdf")
    await lib.settle()

    (doc,) = lib.service.state().documents
    assert doc.id == doc_id
    assert doc.status == DocumentStatus.FAILED
    assert doc.error is not None
    assert "PDF" in doc.error


async def test_documents_wait_for_the_model_then_index_on_request(tmp_path: Path) -> None:
    harness = Harness(tmp_path, FakeEmbedderResolver(ready=False))
    await harness.service.start()
    try:
        doc_id = harness.import_bytes(SLEEP_PDF, "sleep.pdf")
        await harness.settle()
        state = harness.service.state()
        assert state.documents[0].status == DocumentStatus.READY
        assert not state.documents[0].searchable
        assert state.index.pending_documents == 1
        assert not state.index.model_ready
        with pytest.raises(ModelNotReadyError):
            await harness.service.search(SearchRequest(query="sleep"))

        harness.embedders.ready = True
        harness.service.reindex()
        await harness.settle()
        assert harness.service.state().documents[0].searchable
        assert harness.service.index_status().pending_documents == 0
        assert harness.status(doc_id) == DocumentStatus.READY
    finally:
        await harness.service.stop()


async def test_switching_embedding_model_needs_reindex(lib: Harness) -> None:
    lib.import_bytes(SLEEP_PDF, "sleep.pdf")
    await lib.settle()

    lib.embedders.model_id = "embed-other"  # e.g. the user picked another tier
    status = lib.service.index_status()
    assert (status.embedding_model, status.pending_documents) == ("embed-other", 1)

    lib.service.reindex()
    await lib.settle()
    assert lib.service.index_status().pending_documents == 0
    results = await lib.service.search(SearchRequest(query="sleep memory"))
    assert results.embedding_model == "embed-other"
    assert len(results.results) == 1


async def test_delete_removes_document_file_and_index_rows(lib: Harness) -> None:
    doc_id = lib.import_bytes(SLEEP_PDF, "sleep.pdf")
    await lib.settle()

    assert await lib.service.delete(doc_id)
    assert lib.service.state().documents == []
    assert not (lib.root / "files" / f"{doc_id}.pdf").exists()
    assert (await lib.service.search(SearchRequest(query="sleep"))).results == []
    assert not await lib.service.delete(doc_id)


async def test_interrupted_imports_resume_on_start(tmp_path: Path) -> None:
    first = Harness(tmp_path, FakeEmbedderResolver())
    doc_id = first.import_bytes(SLEEP_PDF, "sleep.pdf")  # queued, but the worker never ran

    second = Harness(tmp_path, FakeEmbedderResolver())
    await second.service.start()
    try:
        await second.settle()
        assert second.status(doc_id) == DocumentStatus.READY
    finally:
        await second.service.stop()


def _doc(doc_id: str) -> Document:
    return Document(
        id=doc_id,
        file_name=f"{doc_id}.pdf",
        size_bytes=1,
        added_at="2026-10-25T00:00:00Z",
        status=DocumentStatus.READY,
        metadata=DocumentMetadata(title=doc_id),
    )


def _passage(doc_id: str, index: int) -> Passage:
    return Passage(
        id=f"{doc_id}:{index}",
        document_id=doc_id,
        index=index,
        page=index + 1,
        text=f"text {index}",
        language="en",
        sentences=[],
    )


def test_group_hits_keeps_only_nearly_best_passages() -> None:
    hits = [
        IndexHit("a:0", "a", score=0.033, similarity=0.86),
        IndexHit("b:0", "b", score=0.016, similarity=0.79),
        IndexHit("a:1", "a", score=0.015, similarity=0.84),
        IndexHit("a:2", "a", score=0.010, similarity=0.79),  # e.g. a reference list
        IndexHit("gone:0", "gone", score=0.5, similarity=0.99),  # deleted document
    ]
    documents = {d: _doc(d) for d in ("a", "b")}
    passages = {h.passage_id: _passage(h.document_id, int(h.passage_id[-1])) for h in hits}

    results = group_hits(hits, documents, passages)

    assert [r.document.id for r in results] == ["a", "b"]
    assert [p.passage_id for p in results[0].passages] == ["a:0", "a:1"]
    assert results[0].score == 0.033


async def test_reference_lists_are_stored_but_not_indexed(lib: Harness) -> None:
    doc_id = lib.import_bytes(PAPER_WITH_REFERENCES_PDF, "paper.pdf")
    await lib.settle()

    stored = lib.service._repo.passages_for_document(doc_id)
    (references,) = [p for p in stored if p.page == 4]
    assert references.kind == "references"
    index = LanceIndexStore(lib.root / "index").open("embed-test")
    assert index is not None
    vector = FakeEmbedder().embed_queries([references.text])[0]
    hits = index.search(vector, search_form(references.text), None, 100)
    assert {h.passage_id for h in hits} == {p.id for p in stored if p.page < 4}


def test_searchable_passages_skip_boilerplate_unless_nothing_else_is_left() -> None:
    body, refs = _passage("a", 0), _passage("a", 1).model_copy(update={"kind": "references"})
    assert searchable_passages([body, refs]) == [body]
    assert searchable_passages([refs]) == [refs]


async def test_reparsing_drops_stale_index_rows(tmp_path: Path) -> None:
    first = Harness(tmp_path, FakeEmbedderResolver())
    await first.service.start()
    doc_id = first.import_bytes(SLEEP_PDF, "sleep.pdf")
    await first.settle()
    await first.service.stop()
    assert first.service.index_status().indexed_documents == 1
    # What the v2 schema migration does to documents parsed before passage kinds existed.
    first.service._repo.set_status(doc_id, DocumentStatus.QUEUED)

    second = Harness(tmp_path, FakeEmbedderResolver(ready=False))
    await second.service.start()
    try:
        await second.settle()
        assert second.status(doc_id) == DocumentStatus.READY
        # Parsed again, so the old rows are gone and the document waits for "index now".
        assert second.service.index_status().pending_documents == 1
    finally:
        await second.service.stop()

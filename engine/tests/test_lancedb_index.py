from pathlib import Path

import numpy as np
import pytest

from rb_engine.adapters.store.lancedb_index import LanceIndexStore, LancePassageIndex
from rb_engine.ports.library import IndexedPassage
from rb_engine.text.search_form import search_form


def _vec(*values: float) -> np.ndarray:
    v = np.zeros(8, dtype=np.float32)
    v[: len(values)] = values
    return v / np.linalg.norm(v)


def _passage(pid: str, doc: str, lang: str, text: str, vector: np.ndarray) -> IndexedPassage:
    return IndexedPassage(
        passage_id=pid, document_id=doc, language=lang, search_text=search_form(text), vector=vector
    )


@pytest.fixture
def index(tmp_path: Path) -> LancePassageIndex:
    store = LanceIndexStore(tmp_path)
    created = store.open("embed-test", dimension=8)
    assert created is not None
    created.add(
        [
            _passage("d1:0", "d1", "en", "Sleep improves memory consolidation", _vec(1, 0.1)),
            _passage("d1:1", "d1", "en", "Participants learned word pairs", _vec(0.8, 0.5)),
            _passage("d2:0", "d2", "en", "Heat waves reduce wheat yields", _vec(0, 1)),
            _passage("d3:0", "d3", "he", "והמחקר בדק את השפעת השינה", _vec(0.9, 0, 0.3)),
        ]
    )
    return created


def test_open_without_dimension_does_not_create(tmp_path: Path) -> None:
    assert LanceIndexStore(tmp_path).open("missing") is None


def test_vector_and_keyword_hits_are_fused(index: LancePassageIndex) -> None:
    hits = index.search(_vec(1, 0.1), search_form("sleep memory"), None, limit=10)
    assert hits[0].passage_id == "d1:0"
    assert hits[0].similarity == pytest.approx(1.0, abs=1e-4)
    assert {h.document_id for h in hits} >= {"d1", "d3"}


def test_language_filter(index: LancePassageIndex) -> None:
    hits = index.search(_vec(1, 0.1), search_form("sleep"), "he", limit=10)
    assert [h.document_id for h in hits] == ["d3"]


def test_hebrew_keyword_matches_across_prefixes(index: LancePassageIndex) -> None:
    # The query vector points away from d3; only the keyword "מחקר" can find "והמחקר".
    hits = index.search(_vec(0, 1), search_form("מחקר"), None, limit=2)
    assert "d3" in {h.document_id for h in hits}


def test_delete_and_document_ids(index: LancePassageIndex) -> None:
    assert index.document_ids() == {"d1", "d2", "d3"}
    index.delete_document("d1")
    assert index.document_ids() == {"d2", "d3"}
    assert all(h.document_id != "d1" for h in index.search(_vec(1), "sleep", None, 10))


def test_rows_added_after_index_creation_are_searchable(index: LancePassageIndex) -> None:
    index.add([_passage("d4:0", "d4", "en", "Glacier retreat in the Alps", _vec(0, 0, 0, 1))])
    hits = index.search(_vec(0, 0, 0, 1), search_form("glacier"), None, limit=1)
    assert hits[0].document_id == "d4"


def test_index_persists_across_store_instances(tmp_path: Path, index: LancePassageIndex) -> None:
    reopened = LanceIndexStore(tmp_path).open("embed-test")
    assert reopened is not None
    assert reopened.document_ids() == {"d1", "d2", "d3"}


def test_rejects_unsafe_ids(index: LancePassageIndex) -> None:
    with pytest.raises(ValueError, match="unsafe"):
        index.delete_document("x' OR '1'='1")

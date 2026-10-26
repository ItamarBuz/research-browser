import textwrap
from pathlib import Path

import pytest

from rb_engine.adapters.pdf.pdfium_parser import PdfiumParser
from rb_engine.domain.errors import DocumentParseError
from rb_engine.ports.library import RawPdf
from rb_engine.services.document_parser import find_doi, parse_document
from tests.boilerplate_samples import (
    APA_REFERENCES,
    HEBREW_PROSE,
    LIGO_AUTHOR_LIST,
    LIGO_REFERENCES,
)
from tests.pdfs import SLEEP_PAPER_PAGES, make_pdf


@pytest.fixture
def sleep_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "sleep.pdf"
    path.write_bytes(make_pdf(SLEEP_PAPER_PAGES, {"Author": "Ada Lovelace; Alan Turing"}))
    return path


def test_extracts_page_text(sleep_pdf: Path) -> None:
    raw = PdfiumParser().extract(sleep_pdf)
    assert len(raw.pages) == 3
    assert "Forty participants" in raw.pages[1]
    assert raw.info["Author"] == "Ada Lovelace; Alan Turing"


def test_rejects_non_pdf(tmp_path: Path) -> None:
    path = tmp_path / "fake.pdf"
    path.write_bytes(b"not a pdf at all")
    with pytest.raises(DocumentParseError, match="Not a readable PDF"):
        PdfiumParser().extract(path)


def test_parses_metadata_language_and_passages(sleep_pdf: Path) -> None:
    parsed = parse_document(PdfiumParser().extract(sleep_pdf), "doc1", "sleep.pdf")

    assert parsed.metadata.title == "Sleep and Memory Consolidation in Adults"
    assert parsed.metadata.authors == ["Ada Lovelace", "Alan Turing"]
    assert parsed.metadata.doi == "10.1234/jts.2021.0042"
    assert parsed.language == "en"
    assert [p.page for p in parsed.passages] == [1, 2, 3]
    assert parsed.passages[0].id == "doc1:0"


def test_running_headers_and_page_numbers_are_dropped(sleep_pdf: Path) -> None:
    parsed = parse_document(PdfiumParser().extract(sleep_pdf), "doc1", "sleep.pdf")
    page_two = parsed.passages[1].text
    assert page_two.startswith("Methods. Forty participants")
    assert "Journal of Test Studies" not in page_two
    assert "Page 2" not in page_two


def test_sentence_spans_point_into_raw_page_text(sleep_pdf: Path) -> None:
    raw = PdfiumParser().extract(sleep_pdf)
    parsed = parse_document(raw, "doc1", "sleep.pdf")
    page = raw.pages[2]
    heading, finding, critique = parsed.passages[2].sentences
    assert page[heading.start : heading.end] == "Results."
    assert page[finding.start : finding.end] == "Recall improved by 21 percent after sleep."
    # A sentence that wraps across lines maps to a raw span containing the line break.
    assert "\n" in page[critique.start : critique.end]
    assert page[critique.start : critique.end].split() == (
        "Critics argue that circadian timing, not sleep itself, explains the improvement.".split()
    )


def test_scanned_pdf_without_text_is_rejected() -> None:
    with pytest.raises(DocumentParseError, match="OCR"):
        parse_document(RawPdf(pages=["", " "], info={}), "doc", "scan.pdf")


def test_title_comes_from_the_largest_font_on_page_one(tmp_path: Path) -> None:
    # Modeled on real arXiv papers: a notice in body size above a two-line title, and the
    # arXiv side stamp set even larger than the title.
    path = tmp_path / "paper.pdf"
    lines = [
        ("arXiv:2005.11401v4 [cs.CL] 12 Apr 2021", 20.0),
        "Provided proper attribution is provided, the authors grant permission to reproduce.",
        ("Retrieval-Augmented Generation for", 17.0),
        ("Knowledge-Intensive NLP Tasks", 17.0),
        "Patrick Lewis, Ethan Perez",
        "Abstract. Large pre-trained language models store factual knowledge in parameters.",
        "They still struggle to access and precisely manipulate that knowledge, which limits",
        "their performance on knowledge-intensive tasks such as open-domain question answering.",
    ]
    path.write_bytes(make_pdf([lines], {"Title": "Rob Sumners (Eds.): Workshop Proceedings"}))

    parsed = parse_document(PdfiumParser().extract(path), "doc", "paper.pdf")

    assert (
        parsed.metadata.title == "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks"
    )


def test_placeholder_authors_are_dropped() -> None:
    raw = RawPdf(pages=["Some words here. " * 20], info={"Author": "1111"})
    assert parse_document(raw, "d", "x.pdf").metadata.authors == []


def test_title_falls_back_to_file_name() -> None:
    raw = RawPdf(pages=["x" * 300], info={"Title": "Microsoft Word - draft7.docx"})
    assert parse_document(raw, "d", "my paper.pdf").metadata.title == "my paper.pdf"


@pytest.mark.parametrize(
    ("text", "doi"),
    [
        ("see https://doi.org/10.1038/nature12373.", "10.1038/nature12373"),
        ("DOI: 10.1016/J.CELL.2020.01.001; received", "10.1016/j.cell.2020.01.001"),
        ("no identifier here", None),
    ],
)
def test_find_doi(text: str, doi: str | None) -> None:
    assert find_doi(text) == doi


def test_reference_list_is_marked_and_kept(tmp_path: Path) -> None:
    path = tmp_path / "paper.pdf"
    references_page = ["References", *textwrap.wrap(LIGO_REFERENCES, 90)]
    path.write_bytes(make_pdf([*SLEEP_PAPER_PAGES, references_page]))

    parsed = parse_document(PdfiumParser().extract(path), "doc1", "paper.pdf")

    kinds = {(p.page, p.kind) for p in parsed.passages}
    assert kinds == {(1, "body"), (2, "body"), (3, "body"), (4, "references")}
    assert "Bolton" in next(p.text for p in parsed.passages if p.page == 4)


def test_reference_and_author_lists_do_not_vote_on_the_language() -> None:
    # A Hebrew paper whose author and reference lists are in English is still Hebrew.
    raw = RawPdf(pages=[HEBREW_PROSE, LIGO_AUTHOR_LIST, LIGO_REFERENCES, APA_REFERENCES], info={})
    parsed = parse_document(raw, "doc", "hebrew.pdf")
    assert [p.kind for p in parsed.passages] == ["body", "author_list", "references", "references"]
    assert parsed.language == "he"

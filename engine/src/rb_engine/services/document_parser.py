"""Turns a raw PDF into metadata, language and sentence-aware passages."""

import re
import statistics
from collections import Counter
from collections.abc import Sequence

from rb_engine.domain.errors import DocumentParseError
from rb_engine.domain.library import DocumentMetadata, ParsedDocument, Passage, SentenceSpan
from rb_engine.ports.library import RawPdf, SizedLine
from rb_engine.text.boilerplate import classify_passages
from rb_engine.text.clean import MappedText, clean_page_text, find_repeated_lines
from rb_engine.text.language import SourceLanguage, detect_language
from rb_engine.text.segment import build_passages, split_sentences

MIN_TEXT_CHARS = 200
"""Below this, the PDF is most likely scanned images; OCR is not supported yet."""
PASSAGE_MAX_WORDS = 120
LANGUAGE_SAMPLE_CHARS = 20_000

_DOI = re.compile(r"\b10\.\d{4,9}/[^\s\"<>]+", re.IGNORECASE)
_PDF_DATE_YEAR = re.compile(r"^D?:?((?:19|20)\d{2})")
_JUNK_TITLE = re.compile(r"^(untitled|microsoft word|document\d*|.*\.(docx?|pdf|tex|dvi))", re.I)
_AUTHOR_SPLIT = re.compile(r"\s*(?:;|,| and | & )\s*")
_ARXIV_STAMP = re.compile(r"^arXiv:\d{4}\.\d{4,5}", re.I)
MIN_TITLE_WORDS = 2
MAX_TITLE_CHARS = 300
MAX_TITLE_LINES = 4
TITLE_SIZE_TOLERANCE = 0.95
MIN_TITLE_SIZE_RATIO = 1.15
"""The title font must be at least this much larger than the typical (median) line."""


def find_doi(text: str) -> str | None:
    match = _DOI.search(text)
    if match is None:
        return None
    return match.group().rstrip(".,;)]}").lower()


def _metadata_title(info: dict[str, str]) -> str | None:
    return _plausible_title(info.get("Title", ""))


def _plausible_title(text: str) -> str | None:
    title = " ".join(text.split())
    if len(title.split()) < MIN_TITLE_WORDS or len(title) > MAX_TITLE_CHARS:
        return None
    if _JUNK_TITLE.match(title) or _ARXIV_STAMP.match(title):
        return None
    return title


def _font_size_title(lines: Sequence[SizedLine]) -> str | None:
    """The run of consecutive page-1 lines set in the largest font: how titles are typeset."""
    candidates = [line for line in lines if not _ARXIV_STAMP.match(line.text.strip())]
    if not candidates:
        return None
    largest = max(line.size for line in candidates)
    if largest < statistics.median(line.size for line in candidates) * MIN_TITLE_SIZE_RATIO:
        return None  # no line stands out, so there is no typographic title to find
    threshold = largest * TITLE_SIZE_TOLERANCE
    start = next(i for i, line in enumerate(candidates) if line.size >= threshold)
    title_lines: list[str] = []
    for line in candidates[start : start + MAX_TITLE_LINES]:
        if line.size < threshold:
            break
        title_lines.append(line.text)
    # Clean like body text so line-end hyphens ("cli-\nmate") are joined.
    return _plausible_title(clean_page_text("\n".join(title_lines)).text)


def _first_lines_title(first_page: str) -> str | None:
    for raw_line in first_page.splitlines():
        title = _plausible_title(raw_line)
        if title:
            return title
    return None


def extract_metadata(raw: RawPdf, cleaned_pages: Sequence[str], file_name: str) -> DocumentMetadata:
    first_page = raw.pages[0] if raw.pages else ""
    title = (
        _font_size_title(raw.first_page_lines)
        or _metadata_title(raw.info)
        or _first_lines_title(first_page)
        or file_name
    )
    authors = [
        a
        for a in _AUTHOR_SPLIT.split(raw.info.get("Author", "").strip())
        if any(ch.isalpha() for ch in a)  # drop placeholders such as "1111"
    ]
    year_match = _PDF_DATE_YEAR.match(raw.info.get("CreationDate", ""))
    return DocumentMetadata(
        title=title,
        authors=authors,
        year=int(year_match.group(1)) if year_match else None,
        doi=find_doi(" ".join(cleaned_pages[:2])),
    )


def _document_language(cleaned_pages: Sequence[str]) -> SourceLanguage:
    sample = " ".join(cleaned_pages)[:LANGUAGE_SAMPLE_CHARS]
    return detect_language(sample)


def _page_passages(
    document_id: str, page_number: int, cleaned: MappedText, start_index: int
) -> list[Passage]:
    text = cleaned.text
    passages: list[Passage] = []
    for offset, group in enumerate(build_passages(text, split_sentences(text), PASSAGE_MAX_WORDS)):
        passage_text = text[group[0].start : group[-1].end]
        index = start_index + offset
        passages.append(
            Passage(
                id=f"{document_id}:{index}",
                document_id=document_id,
                index=index,
                page=page_number,
                text=passage_text,
                language=detect_language(passage_text),
                sentences=[
                    SentenceSpan(start=s, end=e)
                    for s, e in (cleaned.source_span(span.start, span.end) for span in group)
                ],
            )
        )
    return passages


def parse_document(raw: RawPdf, document_id: str, file_name: str) -> ParsedDocument:
    repeated = find_repeated_lines(raw.pages)
    cleaned = [clean_page_text(page, repeated) for page in raw.pages]
    if sum(len(page.text) for page in cleaned) < MIN_TEXT_CHARS:
        raise DocumentParseError(
            "This PDF has almost no extractable text (it may be a scanned image). "
            "Text recognition (OCR) is not supported yet."
        )

    passages: list[Passage] = []
    for page_number, page in enumerate(cleaned, start=1):
        passages.extend(_page_passages(document_id, page_number, page, len(passages)))
    kinds = classify_passages([p.text for p in passages])
    passages = [
        p.model_copy(update={"kind": kind}) for p, kind in zip(passages, kinds, strict=True)
    ]

    # The language most prose passages are in wins (a Hebrew paper with an English abstract
    # is Hebrew); reference lists, author lists and tables ("other") do not get a vote.
    prose = Counter(p.language for p in passages if p.kind == "body" and p.language != "other")
    language = (
        prose.most_common(1)[0][0] if prose else _document_language([p.text for p in cleaned])
    )

    return ParsedDocument(
        metadata=extract_metadata(raw, [p.text for p in cleaned], file_name),
        language=language,
        pages=raw.pages,
        passages=passages,
    )

"""Text extraction with PDFium (pypdfium2, Apache-2.0/BSD-3-Clause)."""

import re
import threading
from pathlib import Path

import pypdfium2 as pdfium

from rb_engine.domain.errors import DocumentParseError
from rb_engine.ports.library import RawPdf, SizedLine

# PDFium is not thread-safe; every call into it must hold this lock.
PDFIUM_LOCK = threading.Lock()

_LINE_BREAK = re.compile(r"\r\n|[\r\n]")


def _sized_lines(textpage: pdfium.PdfTextPage, text: str) -> list[SizedLine]:
    """Lines of a page with the largest font size used in each (for title detection).

    PDFium's text and character indices line up one to one, including the line breaks it
    generates, so character i of `text` has font size FPDFText_GetFontSize(page, i).
    """
    count = textpage.count_chars()
    if count != len(text):
        return []  # unexpected layout; title detection falls back to other signals
    lines: list[SizedLine] = []
    start = 0
    for match in [*_LINE_BREAK.finditer(text), None]:
        end = match.start() if match else len(text)
        if text[start:end].strip():
            size = max(
                pdfium.raw.FPDFText_GetFontSize(textpage.raw, i)
                for i in range(start, end)
                if not text[i].isspace()
            )
            lines.append(SizedLine(text=text[start:end], size=float(size)))
        start = match.end() if match else end
    return lines


class PdfiumParser:
    def extract(self, path: Path) -> RawPdf:
        with PDFIUM_LOCK:
            try:
                pdf = pdfium.PdfDocument(path)
            except pdfium.PdfiumError as exc:
                raise DocumentParseError(f"Not a readable PDF: {exc}") from exc
            try:
                info = {k: v for k, v in pdf.get_metadata_dict(skip_empty=True).items() if v}
                pages: list[str] = []
                first_page_lines: list[SizedLine] = []
                for index in range(len(pdf)):
                    page = pdf[index]
                    try:
                        textpage = page.get_textpage()
                        try:
                            text = textpage.get_text_range()
                            pages.append(text)
                            if index == 0:
                                first_page_lines = _sized_lines(textpage, text)
                        finally:
                            textpage.close()
                    finally:
                        page.close()
            except pdfium.PdfiumError as exc:
                raise DocumentParseError(f"Could not read PDF text: {exc}") from exc
            finally:
                pdf.close()
        return RawPdf(pages=pages, info=info, first_page_lines=first_page_lines)

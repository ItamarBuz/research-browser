"""Cleans text extracted from PDF pages while remembering where every character came from.

PDF text arrives with hard line breaks, words hyphenated across lines, ligatures (U+FB01
"ﬁ") and running headers/footers. Search and embedding need clean prose, but highlighting
needs positions in the page's original text, so cleaning produces a `MappedText`: the
cleaned string plus, for each of its characters, the index of the raw character it came from.
"""

import re
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

LINE_BREAKS = frozenset("\r\n\x0b\x0c  ")
HYPHENS = frozenset("-‐­")  # hyphen-minus, hyphen, soft hyphen
SOFT_HYPHEN = "­"
PDFIUM_LINE_HYPHEN = "￾"
"""PDFium reports a hyphen that ends a line as U+FFFE (a noncharacter), e.g. "knowl\\ufffeedge"."""

# Running headers/footers: a line repeated on this share of pages (and at least this many
# pages) is treated as page furniture, not content.
REPEATED_LINE_MIN_SHARE = 0.4
REPEATED_LINE_MIN_PAGES = 3
_DIGITS = re.compile(r"\d+")


@dataclass(frozen=True, slots=True)
class MappedText:
    text: str
    source_index: tuple[int, ...]
    """source_index[i] is the position in the raw text that produced text[i]."""

    def source_span(self, start: int, end: int) -> tuple[int, int]:
        """Raw-text span covering cleaned characters [start, end)."""
        if start >= end:
            raise ValueError("empty span")
        return self.source_index[start], self.source_index[end - 1] + 1


def _line_key(line: str) -> str:
    # Page numbers differ per page ("Page 3 of 12"), so digits are ignored for matching.
    return _DIGITS.sub("#", " ".join(line.split())).casefold()


def find_repeated_lines(pages: Sequence[str]) -> frozenset[str]:
    """Line keys that look like running headers or footers across the document."""
    if len(pages) < REPEATED_LINE_MIN_PAGES:
        return frozenset()
    counts: Counter[str] = Counter()
    for page in pages:
        keys = {_line_key(line) for line in _split_lines(page)}
        counts.update(key for key in keys if key)
    threshold = max(REPEATED_LINE_MIN_PAGES, len(pages) * REPEATED_LINE_MIN_SHARE)
    return frozenset(key for key, n in counts.items() if n >= threshold)


def _split_lines(raw: str) -> list[str]:
    return re.split(r"\r\n|[\r\n\x0b\x0c  ]", raw)


def _skipped_ranges(raw: str, skip_lines: frozenset[str]) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    if not skip_lines:
        return ranges
    for match in re.finditer(r"[^\r\n\x0b\x0c  ]+", raw):
        if _line_key(match.group()) in skip_lines:
            ranges.append(match.span())
    return ranges


def _hyphenation_resume(raw: str, i: int, previous: str | None) -> int | None:
    """If raw[i] is an end-of-line hyphen inside a word ("inter-\\nnational"), return the
    index where the word continues; otherwise None."""
    ch = raw[i]
    if ch not in HYPHENS and ch != PDFIUM_LINE_HYPHEN:
        return None
    if previous is None or not previous.isalpha():
        return None
    j = i + 1
    while j < len(raw) and raw[j] in LINE_BREAKS:
        j += 1
    # PDFium's marker already means "hyphen at a line end", even when no break follows it.
    at_line_end = j > i + 1 or ch == PDFIUM_LINE_HYPHEN
    if at_line_end and j < len(raw) and raw[j].islower():
        return j
    return None


class _Builder:
    def __init__(self) -> None:
        self.chars: list[str] = []
        self.sources: list[int] = []

    def last(self) -> str | None:
        return self.chars[-1] if self.chars else None

    def add(self, ch: str, source: int) -> None:
        if ch.isspace():
            if not self.chars or self.chars[-1] == " ":
                return  # collapse runs of whitespace and drop leading space
            ch = " "
        self.chars.append(ch)
        self.sources.append(source)

    def build(self) -> MappedText:
        while self.chars and self.chars[-1] == " ":
            self.chars.pop()
            self.sources.pop()
        return MappedText(text="".join(self.chars), source_index=tuple(self.sources))


def clean_page_text(raw: str, skip_lines: frozenset[str] = frozenset()) -> MappedText:
    """Join lines into prose, undo end-of-line hyphenation, apply NFKC and collapse spaces."""
    skipped = iter(_skipped_ranges(raw, skip_lines))
    next_skip = next(skipped, None)
    builder = _Builder()

    i = 0
    while i < len(raw):
        if next_skip is not None and i >= next_skip[0]:
            i, next_skip = next_skip[1], next(skipped, None)
            continue
        ch = raw[i]
        resume = _hyphenation_resume(raw, i, builder.last())
        if resume is not None:
            i = resume
            continue
        if ch == PDFIUM_LINE_HYPHEN:
            builder.add("-", i)  # a real hyphen that fell at a line end ("post-Newtonian")
        elif ch != SOFT_HYPHEN:
            for normalized in unicodedata.normalize("NFKC", ch):
                builder.add(normalized, i)
        i += 1
    return builder.build()

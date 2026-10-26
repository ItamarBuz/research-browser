"""Rule-based sentence splitting and passage building for English and Hebrew prose.

Good enough for retrieval and highlighting, and cheap enough for Lite machines. A model-based
segmenter can replace `split_sentences` later behind the same signature.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

# Words that end with a period without ending the sentence (lowercased, without the period).
ABBREVIATIONS = frozenset(
    "e.g i.e et al cf vs etc fig figs eq eqs no nos vol vols pp p ch sec ref refs approx "
    "dr mr mrs ms prof st jr sr inc ltd co dept univ ed eds resp viz ca est tab".split()
)

_BOUNDARY = re.compile(
    r"""
    (?P<end>[.!?…]+)          # terminal punctuation
    (?P<close>["'”’)\]]*) # closing quotes or brackets that belong to the sentence
    \s+
    (?=["'“‘(\[]?[A-Z0-9א-ת])  # next sentence starts like a sentence
    """,
    re.VERBOSE,
)
_LAST_TOKEN = re.compile(r"(\S+)$")


@dataclass(frozen=True, slots=True)
class Span:
    start: int
    end: int


def _is_abbreviation(text: str, period_at: int) -> bool:
    match = _LAST_TOKEN.search(text, 0, period_at)
    if match is None:
        return False
    token = match.group(1).lstrip("(\"'[").lower()
    if token in ABBREVIATIONS:
        return True
    # Initials such as "J." in "J. Smith" or "U.S."
    return bool(re.fullmatch(r"(?:[a-z]\.)*[a-z]", token))


def split_sentences(text: str) -> list[Span]:
    spans: list[Span] = []
    start = 0
    for match in _BOUNDARY.finditer(text):
        end_punct = match.start("end")
        if match.group("end") == "." and _is_abbreviation(text, end_punct):
            continue
        end = match.end("close")
        if text[start:end].strip():
            spans.append(Span(start, end))
        start = match.end()
    if text[start:].strip():
        spans.append(Span(start, len(text.rstrip())))
    return spans


def build_passages(text: str, sentences: Sequence[Span], max_words: int = 120) -> list[list[Span]]:
    """Group consecutive sentences into passages of at most `max_words` words.

    A single sentence longer than the limit becomes its own passage; the embedder truncates
    it, which is acceptable for retrieval.
    """
    passages: list[list[Span]] = []
    current: list[Span] = []
    words = 0
    for sentence in sentences:
        n = len(text[sentence.start : sentence.end].split())
        if current and words + n > max_words:
            passages.append(current)
            current, words = [], 0
        current.append(sentence)
        words += n
    if current:
        passages.append(current)
    return passages

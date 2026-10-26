"""Recognises passages that are not the paper's content: reference lists and author lists.

Bibliographies and long author/affiliation lists match many queries on names, venues and
topical title words, so they crowd real answers out of search results. They are kept in the
library (nothing is lost) but left out of the search index.

The classifier is rule-based, deterministic and linear in the text length, so it runs on
Lite machines. It reads cheap surface signals, tuned on real arXiv papers:

- citation cues: years, "[12] A. Name" entry starts, "et al.", "Name. 2018." and
  "(2018)." author-year entries, venue words ("Proceedings", "Phys. Rev.", "arXiv", "doi",
  "בתוך", "עמ'"), "12(3):45" volume numbers and initials ("J.", "כהן, א'");
- the share of function words ("the", "of", "של", "את"), which is high in prose and low in
  lists of names and titles;
- comma and capitalised-word density: author lists are "B. P. Abbott,1 R. Abbott,1 ...", and
  every reference entry separates its authors with commas, while tables rarely have any.

A "References"/"מקורות" heading lowers the bar for the passages that follow it, since
entries split across passages often carry fewer cues than whole ones.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

PassageKind = Literal["body", "references", "author_list"]
"""body: the paper's own text, the only searchable kind. references: bibliography entries.
author_list: author names and affiliations."""

ENGLISH_FUNCTION_WORDS = frozenset(
    "a an the of and or to in on at by for with from as into onto over under about after "
    "before between during through without within is are was were be been being has have had "
    "do does did can could may might must shall should will would this that these those it its "
    "we our they their them he she his her which who whom whose what when where while how why "
    "if than then there here not no nor also only both each such more most other some any all "
    "very so but because however thus therefore hence since until".split()
)
HEBREW_FUNCTION_WORDS = frozenset(
    "של את על עם אל מן עד בין לפי כמו אחרי לפני בתוך תוך מול ללא בלי אצל עבור כדי בגלל "
    "הוא היא הם הן זה זו זאת אלה אלו אני אנו אנחנו אתה אתם הזה הזאת האלה "
    "כי אשר אם או גם לא אין יש אך אבל רק אף עוד כבר כאשר אלא כך כן לכן מאוד יותר פחות "
    "היה היתה הייתה היו יהיה להיות ידי בו בה בהם בהן לו לה להם להן שלו שלה שלהם מה מי איך "
    "כל כלל אחד אחת שני שתי".split()
)

_WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")
_HEBREW_LETTER = re.compile(r"[א-ת]")
_YEAR = re.compile(r"(?<![\d.,])(?:1[6-9]|20)\d{2}[a-z]?(?!\d)")
_AUTHOR_YEAR = re.compile(
    r"(?<=[.,]\s)(?:1[6-9]|20)\d{2}[a-z]?\.(?=\s|$)"  # "Jan Hajic. 2018. Title" (ACL)
    r"|\((?:1[6-9]|20)\d{2}[a-z]?\)\s?[.:,]"  # "Smith, J. (2018). Title" (APA)
)
_ENTRY_START = re.compile(r"(?:^|\s)\[\d{1,3}\]\s+(?=[A-Z][\w’'-]*[.,\s])")
_ET_AL = re.compile(r"\bet\s+al\b")
_VENUE = re.compile(
    r"\b(?:Proceedings|Proc\.|Conference|Conf\.|Journal|J\.|Transactions|Trans\.|Rev\.|"
    r"Lett\.|Phys\.|pp\.|vol\.|Vol\.|pages\s+\d|arXiv|doi|DOI|ISBN|ISSN|Workshop|Symposium|"
    r"preprint|Press|Publishers|Springer|Elsevier|IEEE|ACM)(?!\w)"
    r"|https?://"
    r"|(?:הוצאת|כתב העת|בתוך|עמ['׳])"
)
_VOLUME = re.compile(r"\d+\s?\(\d+\)\s?[:,]\s?\d+")
_INITIAL = re.compile(r"(?<![\w.'’-])[A-Z]\.(?=[\s,-]|[A-Z]\.)|(?<![א-ת])[א-ת]['׳](?=[\s,.;])")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_REFERENCES_HEADING = re.compile(
    # A heading, not a mention: not preceded by a lowercase word ("see the References").
    r"(?<![\w-])(?<![a-zא-ת,;] )"
    r"(?:References|REFERENCES|Bibliography|BIBLIOGRAPHY|Works Cited|Literature Cited|"
    r"רשימת מקורות|מקורות|ביבליוגרפיה|רשימה ביבליוגרפית)"
    r"(?=\s|$)"
)

MIN_WORDS = 5
"""Shorter passages carry too little evidence to be classified as boilerplate."""

INITIAL_WEIGHT = 0.5
"""Initials also occur in prose ("J. Smith showed"), so each counts as half a cue."""

REFERENCES_MIN_CUES = 14.0
"""Citation cues per 100 tokens. Prose that cites heavily ("Smith et al. (2019) ...") stays
below 10; reference lists in the sample papers score 14-60."""
REFERENCES_MAX_FUNCTION_SHARE = 0.22
"""English prose is 25-55% function words; reference entries are mostly names and titles."""
HEBREW_REFERENCES_MAX_FUNCTION_SHARE = 0.12
"""Hebrew attaches prepositions and articles to words (ב, ל, ה), so its prose has fewer
stand-alone function words than English."""
REFERENCES_MIN_COMMAS = 0.07
"""Commas per token. Reference entries list authors with commas; tables that cite sources
("Zhu et al. (2013) [40] 90.4") have almost none."""
REFERENCES_MIN_YEARS = 1.5
"""Years per 100 tokens. Every entry has a year; a list of names without years is an author
list. Inside a references section this is not required, since an entry's tail ("Harvard Law
Review 132 (2), pp. 536-601.") may be a passage of its own."""
REFERENCES_MIN_NON_YEAR_CUES = 3.0
"""Citation cues other than years, per 100 tokens. Data descriptions ("for the years
1999-2002 and 2003-2007 ...") are full of years but have no initials, venues or entries."""

SECTION_MIN_CUES = 6.0
SECTION_MAX_FUNCTION_SHARE = 0.30
HEBREW_SECTION_MAX_FUNCTION_SHARE = 0.15
SECTION_MIN_COMMAS = 0.04
"""The lower bars for passages after a references heading: ACL-style entries ("Avi Shmidman,
..., and Yoav Goldberg. 2020. Nakdan: Professional Hebrew diacritizer. In Proceedings of the
...") have many function words in their titles and venues, and "[41] K. Simonyan and A.
Zisserman. Very deep ... In ICLR, 2015." has few commas."""
SECTION_END_MAX_CUES = 3.0
"""A passage with more function words than SECTION_MAX_FUNCTION_SHARE and fewer cues than this
reads as prose and ends the section (appendices often follow the references). A single entry
with a wordy title ("Latent retrieval for weakly supervised open domain question answering.
In Proceedings of the ...") must not end it."""

AUTHOR_LIST_MAX_FUNCTION_SHARE = 0.12
AUTHOR_LIST_MIN_COMMAS = 0.25
"""Commas per token: "B. P. Abbott,1 R. Abbott,1 T. D. Abbott,2" has one every two tokens."""
AUTHOR_LIST_MIN_CAPITALISED = 0.75
"""Share of Latin-script words that start with a capital (names, institutions, places)."""
AUTHOR_LIST_MIN_EMAILS = 3
"""A title block listing several e-mail addresses and little else."""


@dataclass(frozen=True, slots=True)
class TextSignals:
    words: int
    function_share: float
    capitalised_share: float
    commas_per_token: float
    years_per_100: float
    citation_cues_per_100: float
    """All cues, years included."""
    emails: int
    hebrew: bool


def text_signals(text: str) -> TextSignals:
    tokens = max(len(text.split()), 1)
    words = _WORD.findall(text)
    latin = [w for w in words if not _HEBREW_LETTER.match(w)]
    hebrew_letters = len(_HEBREW_LETTER.findall(text))
    function_words = sum(
        w.lower() in ENGLISH_FUNCTION_WORDS or w in HEBREW_FUNCTION_WORDS for w in words
    )
    years = len(_YEAR.findall(text))
    cues = (
        years
        + len(_AUTHOR_YEAR.findall(text))
        + len(_ENTRY_START.findall(text))
        + len(_ET_AL.findall(text))
        + len(_VENUE.findall(text))
        + len(_VOLUME.findall(text))
        + INITIAL_WEIGHT * len(_INITIAL.findall(text))
    )
    return TextSignals(
        words=len(words),
        function_share=function_words / max(len(words), 1),
        capitalised_share=sum(w[0].isupper() for w in latin) / len(latin) if latin else 0.0,
        commas_per_token=text.count(",") / tokens,
        years_per_100=years * 100 / tokens,
        citation_cues_per_100=cues * 100 / tokens,
        emails=len(_EMAIL.findall(text)),
        hebrew=hebrew_letters * 2 > sum(ch.isalpha() for ch in text),
    )


def _max_function_share(signals: TextSignals, *, in_references_section: bool) -> float:
    if in_references_section:
        return HEBREW_SECTION_MAX_FUNCTION_SHARE if signals.hebrew else SECTION_MAX_FUNCTION_SHARE
    return HEBREW_REFERENCES_MAX_FUNCTION_SHARE if signals.hebrew else REFERENCES_MAX_FUNCTION_SHARE


def _looks_like_references(signals: TextSignals, *, in_references_section: bool) -> bool:
    if signals.citation_cues_per_100 - signals.years_per_100 < REFERENCES_MIN_NON_YEAR_CUES:
        return False
    if in_references_section:
        min_cues, min_commas = SECTION_MIN_CUES, SECTION_MIN_COMMAS
    elif signals.years_per_100 < REFERENCES_MIN_YEARS:
        return False
    else:
        min_cues, min_commas = REFERENCES_MIN_CUES, REFERENCES_MIN_COMMAS
    max_function_share = _max_function_share(signals, in_references_section=in_references_section)
    return (
        signals.function_share <= max_function_share
        and signals.citation_cues_per_100 >= min_cues
        and signals.commas_per_token >= min_commas
    )


def _looks_like_author_list(signals: TextSignals) -> bool:
    if signals.function_share > AUTHOR_LIST_MAX_FUNCTION_SHARE:
        return False
    if signals.emails >= AUTHOR_LIST_MIN_EMAILS:
        return True
    return (
        signals.commas_per_token >= AUTHOR_LIST_MIN_COMMAS
        and signals.capitalised_share >= AUTHOR_LIST_MIN_CAPITALISED
    )


def _classify(signals: TextSignals, *, in_references_section: bool) -> PassageKind:
    if signals.words < MIN_WORDS:
        return "body"
    # Initials make author lists look citation-dense; without years they are not references.
    if signals.years_per_100 < REFERENCES_MIN_YEARS and _looks_like_author_list(signals):
        return "author_list"
    if _looks_like_references(signals, in_references_section=in_references_section):
        return "references"
    if _looks_like_author_list(signals):
        return "author_list"
    return "body"


def _reads_as_prose(signals: TextSignals) -> bool:
    return (
        signals.words >= MIN_WORDS
        and signals.function_share > _max_function_share(signals, in_references_section=True)
        and signals.citation_cues_per_100 < SECTION_END_MAX_CUES
    )


def classify_passage(text: str, *, in_references_section: bool = False) -> PassageKind:
    return _classify(text_signals(text), in_references_section=in_references_section)


def has_references_heading(text: str) -> bool:
    return _REFERENCES_HEADING.search(text) is not None


def classify_passages(texts: Sequence[str]) -> list[PassageKind]:
    """Classify a document's passages in reading order.

    A references heading opens a references section, which stays open until a passage reads
    as prose again, so entries split across passages are caught.
    """
    kinds: list[PassageKind] = []
    in_section = False
    for text in texts:
        signals = text_signals(text)
        heading = has_references_heading(text)
        kinds.append(_classify(signals, in_references_section=in_section or heading))
        if heading:
            in_section = True
        elif _reads_as_prose(signals):
            in_section = False
    return kinds

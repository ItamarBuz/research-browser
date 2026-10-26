"""Normalized "search form" of text for keyword (BM25) matching in English and Hebrew.

Hebrew attaches prepositions and articles to words ("והמחקר" = "and the research"), so a
plain word index never matches "מחקר". Each Hebrew word is therefore indexed together with
its forms with up to two prefix letters removed. Queries get the same treatment, so both
sides meet. Niqqud is stripped and final letters are unified so spelling variants match.
"""

import re

HEBREW_PREFIX_LETTERS = frozenset("והבכלמש")
MAX_PREFIXES = 2
MIN_STEM_LETTERS = 3

_FINAL_LETTERS = str.maketrans({"ך": "כ", "ם": "מ", "ן": "נ", "ף": "פ", "ץ": "צ"})
_NIQQUD = re.compile(r"[֑-ׇֽֿׁׂׅׄ]")
# Geresh/gershayim (and ASCII stand-ins) inside Hebrew acronyms: ד"ר -> דר
_ACRONYM_MARKS = re.compile(r"(?<=[א-ת])[\"'׳״](?=[א-ת])")
_TOKEN = re.compile(r"[\wא-ת]+")


def _is_hebrew(token: str) -> bool:
    return any("א" <= ch <= "ת" for ch in token)


def _hebrew_variants(token: str) -> list[str]:
    variants = [token]
    stripped = token
    for _ in range(MAX_PREFIXES):
        if len(stripped) - 1 < MIN_STEM_LETTERS or stripped[0] not in HEBREW_PREFIX_LETTERS:
            break
        stripped = stripped[1:]
        variants.append(stripped)
    return variants


def search_form(text: str) -> str:
    text = _NIQQUD.sub("", text)
    text = _ACRONYM_MARKS.sub("", text)
    text = text.translate(_FINAL_LETTERS).casefold()
    terms: list[str] = []
    for token in _TOKEN.findall(text):
        terms.extend(_hebrew_variants(token) if _is_hebrew(token) else [token])
    return " ".join(terms)

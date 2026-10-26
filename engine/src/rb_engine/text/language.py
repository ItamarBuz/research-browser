"""Language detection for the two languages the app supports.

Hebrew has its own script, so letter counts separate it from Latin text reliably. Among
Latin-script texts, a high share of common English function words marks English; anything
else (French, German, ...) is "other", so the English-only filter does not include it.
"""

import re
from typing import Literal

SourceLanguage = Literal["en", "he", "other"]

HEBREW_MIN_SHARE = 0.3
ENGLISH_MIN_STOPWORD_SHARE = 0.08
MIN_LETTERS = 3
SHORT_TEXT_WORDS = 12

_WORD = re.compile(r"[a-z]+")
ENGLISH_STOPWORDS = frozenset(
    "the of and to in a is that for on with as are by this be was were from or an at "
    "which we it not have has these their our can its between than also been more such "
    "how what when where who whether into using used does do did why all any there about "
    "after before during no is it".split()
)


def _is_hebrew_letter(ch: str) -> bool:
    return "א" <= ch <= "ת"


def detect_language(text: str) -> SourceLanguage:
    hebrew = latin = 0
    for ch in text:
        if _is_hebrew_letter(ch):
            hebrew += 1
        elif ch.isascii() and ch.isalpha():
            latin += 1
    letters = hebrew + latin
    if letters < MIN_LETTERS:
        return "other"
    if hebrew / letters >= HEBREW_MIN_SHARE:
        return "he"
    words = _WORD.findall(text.lower())
    if (
        words
        and sum(w in ENGLISH_STOPWORDS for w in words) / len(words) >= ENGLISH_MIN_STOPWORD_SHARE
    ):
        return "en"
    # Short queries ("transformer attention", "staying awake hurt memory") often have no
    # function words; with only Latin letters, English is by far the likeliest language.
    all_ascii = all(ch.isascii() for ch in text if ch.isalpha())  # no é, ü, ß, ...
    if len(text.split()) <= SHORT_TEXT_WORDS and all_ascii:
        return "en"
    return "other"

"""Helpers shared by the source adapters."""

import html
import re
from collections.abc import Callable
from dataclasses import dataclass

from rb_engine.text.language import SourceLanguage, detect_language

MAX_AUTHORS = 20
_TAGS = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class SourceCredentials:
    """Optional, user-provided; every source also works without them (with lower limits)."""

    contact_email: str | None = None
    openalex_api_key: str | None = None
    semantic_scholar_api_key: str | None = None


CredentialsProvider = Callable[[], SourceCredentials]


def clean_text(value: str | None) -> str | None:
    """Strip HTML markup (Europe PMC abstracts) and collapse whitespace."""
    if not value:
        return None
    text = _SPACES.sub(" ", html.unescape(_TAGS.sub(" ", value))).strip()
    return text or None


def language_of(code: str | None, title: str, abstract: str | None) -> SourceLanguage:
    """Map a source's language code; detect from the text when the source has none."""
    mapped = {"en": "en", "eng": "en", "he": "he", "heb": "he"}.get((code or "").lower())
    if mapped == "en":
        return "en"
    if mapped == "he":
        return "he"
    if code:
        return "other"
    return detect_language(f"{title} {abstract or ''}")


def parse_year(value: object) -> int | None:
    try:
        year = int(str(value)[:4])
    except (TypeError, ValueError):
        return None
    return year if 1000 <= year <= 2999 else None

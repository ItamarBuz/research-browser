import pytest

from rb_engine.text.boilerplate import (
    PassageKind,
    classify_passage,
    classify_passages,
    has_references_heading,
)
from tests import boilerplate_samples as s


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        (s.LIGO_AUTHOR_LIST, "author_list"),
        (s.LIGO_AFFILIATIONS, "author_list"),
        (s.LIGO_REFERENCES, "references"),
        (s.APA_REFERENCES, "references"),
        (s.HEBREW_REFERENCES, "references"),
        (s.MIXED_REFERENCES, "references"),
        (s.ATTENTION_TITLE_BLOCK, "body"),
        (s.LIGO_MASSES_TABLE, "body"),
        (s.LIGO_INTRODUCTION, "body"),
        (s.RELATED_WORK, "body"),
        (s.TABLE_CITING_PRIOR_WORK, "body"),
        (s.DATA_DESCRIPTION_WITH_YEARS, "body"),
        (s.DIACRITICS_APPENDIX, "body"),
        (s.HEBREW_PROSE, "body"),
    ],
)
def test_classifies_passages_from_real_papers(text: str, kind: PassageKind) -> None:
    assert classify_passage(text) == kind


def test_short_passages_are_body() -> None:
    assert classify_passage("[51] B. J. Meers, Phys. Rev.") == "body"
    assert classify_passage("") == "body"


def test_acl_style_references_need_a_references_section() -> None:
    # Wordy titles and venues ("In Proceedings of the ...") look like prose on their own.
    assert classify_passage(s.DIACRITICS_REFERENCES) == "body"
    assert classify_passage(s.DIACRITICS_REFERENCES, in_references_section=True) == "references"


def test_references_heading_opens_a_section_until_prose_returns() -> None:
    kinds = classify_passages(
        [
            s.RELATED_WORK,
            s.DIACRITICS_REFERENCES_HEADING,  # acknowledgments, then "References" and entries
            s.DIACRITICS_REFERENCES,
            s.DIACRITICS_REFERENCES_CONTINUED,
            s.DIACRITICS_APPENDIX,
            s.DIACRITICS_REFERENCES,  # the section has ended
        ]
    )
    assert kinds == ["body", "body", "references", "references", "body", "body"]


def test_a_short_entry_tail_does_not_end_the_section() -> None:
    kinds = classify_passages(
        [
            "References",
            "Outside Options and the Labor Market. Discussion Paper.",
            s.DIACRITICS_REFERENCES,
        ]
    )
    assert kinds[-1] == "references"


def test_hebrew_references_heading_opens_a_section() -> None:
    assert has_references_heading(s.HEBREW_REFERENCES)
    assert classify_passages([s.HEBREW_PROSE, "ביבליוגרפיה", s.DIACRITICS_REFERENCES]) == [
        "body",
        "body",
        "references",
    ]


@pytest.mark.parametrize(
    ("text", "heading"),
    [
        ("References [1] Y. Bengio, P. Simard, and P. Frasconi.", True),
        ("This bound is sufficient to establish the claim. ✷ References [1] Irv Bromberg", True),
        ("7 References Abel, W. (2020).", True),
        ("REFERENCES", True),
        ("רשימת מקורות כהן, א' (2010).", True),
        ("as listed in the References section below", False),
        ("Cross-references are resolved later.", False),
        ("מצאנו מקורות רבים לכך", False),
    ],
)
def test_detects_references_headings(text: str, heading: bool) -> None:
    assert has_references_heading(text) == heading

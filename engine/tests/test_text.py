import pytest

from rb_engine.text.clean import clean_page_text, find_repeated_lines
from rb_engine.text.language import detect_language
from rb_engine.text.search_form import search_form
from rb_engine.text.segment import Span, build_passages, split_sentences


def _sentences(text: str) -> list[str]:
    return [text[s.start : s.end] for s in split_sentences(text)]


class TestClean:
    def test_joins_lines_and_collapses_whitespace(self) -> None:
        assert clean_page_text("Deep   learning\r\nmodels  work.\n").text == (
            "Deep learning models work."
        )

    def test_undoes_end_of_line_hyphenation(self) -> None:
        assert clean_page_text("an inter-\nnational study").text == "an international study"

    def test_joins_words_split_by_pdfium_line_hyphen(self) -> None:
        # Seen in real arXiv PDFs: PDFium marks line-end hyphens with U+FFFE.
        assert clean_page_text("prior knowl￾edge is").text == "prior knowledge is"
        assert clean_page_text("interven￾\r\ntions").text == "interventions"

    def test_pdfium_line_hyphen_before_capital_stays_a_hyphen(self) -> None:
        assert clean_page_text("post￾Newtonian theory").text == "post-Newtonian theory"

    def test_keeps_real_hyphens(self) -> None:
        assert clean_page_text("a well-known\nResult").text == "a well-known Result"
        assert clean_page_text("state-of-\nThe art").text == "state-of- The art"

    def test_expands_ligatures_and_maps_back(self) -> None:
        raw = "eﬃcient"  # "ﬃ" ligature
        cleaned = clean_page_text(raw)
        assert cleaned.text == "efficient"
        # all three letters of the ligature point at the single raw character
        assert cleaned.source_index[1:4] == (1, 1, 1)
        assert cleaned.source_span(0, len(cleaned.text)) == (0, len(raw))

    def test_source_spans_point_into_raw_text(self) -> None:
        raw = "First  line of text\r\nsecond line."
        cleaned = clean_page_text(raw)
        start = cleaned.text.index("second")
        raw_start, raw_end = cleaned.source_span(start, start + len("second"))
        assert raw[raw_start:raw_end] == "second"

    def test_removes_repeated_headers(self) -> None:
        bodies = ["Alpha results.", "Beta methods.", "Gamma data.", "Delta notes."]
        pages = [f"Journal of Tests, Vol. 3\n{body}\nPage {n}" for n, body in enumerate(bodies)]
        repeated = find_repeated_lines(pages)
        assert clean_page_text(pages[1], repeated).text == "Beta methods."

    def test_short_documents_keep_all_lines(self) -> None:
        assert find_repeated_lines(["Header\nA", "Header\nB"]) == frozenset()


class TestLanguage:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("The effect of sleep on memory consolidation in adults", "en"),
            ("transformer attention", "en"),
            ("does staying awake all night hurt memory?", "en"),
            ("staying awake impairs recall in young adults", "en"),
            ("effets du sommeil sur la mémoire", "other"),
            ("השפעת השינה על גיבוש הזיכרון אצל מבוגרים", "he"),
            ("מחקר על BERT ו-GPT במשימות הבנת הנקרא", "he"),
            ("Les effets du sommeil sur la mémoire des adultes dans une étude", "other"),
            ("12 34", "other"),
        ],
    )
    def test_detects(self, text: str, expected: str) -> None:
        assert detect_language(text) == expected


class TestSentences:
    def test_splits_simple_sentences(self) -> None:
        assert _sentences("One test. Two tests! Three? Yes.") == [
            "One test.",
            "Two tests!",
            "Three?",
            "Yes.",
        ]

    def test_does_not_split_abbreviations_and_initials(self) -> None:
        text = "As shown by Smith et al. (2020) and in Fig. 3 the effect holds. J. Doe agrees."
        assert _sentences(text) == [
            "As shown by Smith et al. (2020) and in Fig. 3 the effect holds.",
            "J. Doe agrees.",
        ]

    def test_keeps_decimals_and_lowercase_continuations(self) -> None:
        text = "The value was 3.5 percent. results vary. Next sentence."
        assert _sentences(text) == ["The value was 3.5 percent. results vary.", "Next sentence."]

    def test_keeps_closing_quotes_with_sentence(self) -> None:
        assert _sentences('He said "it works." Then left.') == ['He said "it works."', "Then left."]

    def test_splits_hebrew(self) -> None:
        text = "המחקר בדק את ההשפעה. נמצא קשר חזק! האם זה מפתיע?"
        assert _sentences(text) == ["המחקר בדק את ההשפעה.", "נמצא קשר חזק!", "האם זה מפתיע?"]


class TestPassages:
    def test_groups_sentences_up_to_word_limit(self) -> None:
        text = "One two three. Four five six. Seven eight nine. Ten eleven twelve."
        groups = build_passages(text, split_sentences(text), max_words=6)
        assert [[text[s.start : s.end] for s in g] for g in groups] == [
            ["One two three.", "Four five six."],
            ["Seven eight nine.", "Ten eleven twelve."],
        ]

    def test_overlong_sentence_is_its_own_passage(self) -> None:
        text = "x " * 10
        assert build_passages(text, [Span(0, len(text))], max_words=3) == [[Span(0, len(text))]]


class TestSearchForm:
    def test_lowercases_english(self) -> None:
        assert search_form("Deep Learning, NLP!") == "deep learning nlp"

    def test_expands_hebrew_prefixes(self) -> None:
        assert search_form("והמחקר") == "והמחקר המחקר מחקר"

    def test_short_hebrew_words_keep_their_letters(self) -> None:
        assert search_form("של") == "של"
        assert search_form("בית") == "בית"  # stripping ב would leave only two letters

    def test_unifies_final_letters_and_strips_niqqud(self) -> None:
        # ש can be a prefix, so the stripped variant is indexed too.
        assert search_form("שָׁלוֹם") == search_form("שלום") == "שלומ לומ"
        assert search_form("עולם") == "עולמ"

    def test_removes_acronym_marks(self) -> None:
        assert search_form('ד"ר כהן') == search_form("ד״ר כהן") == "דר כהנ"

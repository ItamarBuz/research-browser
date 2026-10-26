"""Marian translation: tokenizer and greedy decoding with scripted sessions; the real-model
check runs only when RB_TEST_TRANSLATOR_DIR points at a downloaded he->en model directory."""

import os
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import sentencepiece as spm

from rb_engine.adapters.translate.marian_onnx import MarianTokenizer, MarianTranslator, load_marian
from rb_engine.domain.catalog import TranslationConfig

CORPUS = [
    "sleep deprivation affects working memory",
    "memory consolidation happens during sleep",
    "students who sleep less remember less",
    "working memory capacity varies between people",
] * 20


@pytest.fixture(scope="module")
def tokenizer(tmp_path_factory: pytest.TempPathFactory) -> MarianTokenizer:
    root = tmp_path_factory.mktemp("spm")
    corpus = root / "corpus.txt"
    corpus.write_text("\n".join(CORPUS), encoding="utf-8")
    spm.SentencePieceTrainer.train(
        input=str(corpus),
        model_prefix=str(root / "m"),
        vocab_size=40,
        hard_vocab_limit=False,
        character_coverage=1.0,
        bos_id=-1,
        eos_id=-1,
        unk_id=0,
        pad_id=-1,
    )
    processor = spm.SentencePieceProcessor(model_file=str(root / "m.model"))
    pieces = [processor.id_to_piece(i) for i in range(processor.get_piece_size())]
    vocab = {"</s>": 0, "<unk>": 1, "<pad>": 2} | {p: i + 3 for i, p in enumerate(pieces)}
    return MarianTokenizer(root / "m.model", root / "m.model", vocab)


def test_encode_appends_eos_and_round_trips(tokenizer: MarianTokenizer) -> None:
    ids = tokenizer.encode("sleep affects memory")
    assert ids[-1] == tokenizer.eos_id
    assert tokenizer.decode(ids) == "sleep affects memory"


class ScriptedDecoder:
    """Emits a fixed token sequence, one per step, then </s>; pad is always the top score."""

    def __init__(self, tokens: list[int], vocab_size: int, pad_id: int, eos_id: int) -> None:
        self.tokens = tokens
        self.vocab_size = vocab_size
        self.pad_id = pad_id
        self.eos_id = eos_id
        self.calls = 0

    def run(self, _names: Any, feeds: dict[str, Any]) -> list[Any]:
        step = feeds["input_ids"].shape[1] - 1
        logits = np.zeros((1, step + 1, self.vocab_size), dtype=np.float32)
        logits[0, -1, self.pad_id] = 100.0  # must be masked by the translator
        target = self.tokens[step] if step < len(self.tokens) else self.eos_id
        logits[0, -1, target] = 50.0
        self.calls += 1
        return [logits]


class FakeEncoder:
    def run(self, _names: Any, feeds: dict[str, Any]) -> list[Any]:
        return [np.zeros((1, feeds["input_ids"].shape[1], 4), dtype=np.float32)]


def test_greedy_decoding_masks_pad_and_stops_at_eos(tokenizer: MarianTokenizer) -> None:
    target_ids = tokenizer.encode("memory sleep")[:-1]
    decoder = ScriptedDecoder(target_ids, 80, tokenizer.pad_id, tokenizer.eos_id)
    translator = MarianTranslator(
        tokenizer, FakeEncoder(), decoder, decoder_start_id=tokenizer.pad_id, max_new_tokens=20
    )
    assert translator.translate("anything") == "memory sleep"
    assert decoder.calls == len(target_ids) + 1


def test_degenerate_repetition_is_cut_off(tokenizer: MarianTokenizer) -> None:
    looping = ScriptedDecoder([10] * 50, 80, tokenizer.pad_id, tokenizer.eos_id)
    translator = MarianTranslator(
        tokenizer, FakeEncoder(), looping, decoder_start_id=tokenizer.pad_id, max_new_tokens=40
    )
    translator.translate("anything")
    assert looping.calls <= 6


def test_empty_text_needs_no_model(tokenizer: MarianTokenizer) -> None:
    translator = MarianTranslator(
        tokenizer, FakeEncoder(), FakeEncoder(), decoder_start_id=0, max_new_tokens=5
    )
    assert translator.translate("   ") == ""


MODEL_DIR = os.environ.get("RB_TEST_TRANSLATOR_DIR")


@pytest.mark.skipif(not MODEL_DIR, reason="RB_TEST_TRANSLATOR_DIR not set")
def test_real_hebrew_to_english() -> None:
    assert MODEL_DIR is not None
    translator = load_marian(Path(MODEL_DIR), TranslationConfig(directory="int8"), threads=2)
    english = translator.translate("האם חוסר שינה פוגע בזיכרון העבודה?").lower()
    assert "sleep" in english
    assert "memory" in english

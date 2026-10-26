"""OPUS-MT (Marian) translation on ONNX Runtime, without PyTorch or transformers.

Mirrors what Hugging Face's MarianTokenizer and greedy generate() do:
- the source text is split into SentencePiece pieces, mapped through the shared vocabulary
  and terminated with </s>;
- the decoder starts from the pad token and repeatedly appends the most likely next token
  (never pad) until </s>;
- target ids are mapped back to pieces and detokenized with the target SentencePiece model.

Queries are short, so the decoder simply re-reads its whole prefix each step instead of
caching attention keys; this keeps the code small at a negligible cost.
"""

import json
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import numpy.typing as npt
import onnxruntime as ort
import sentencepiece as spm

from rb_engine.domain.catalog import TranslationConfig

logger = logging.getLogger(__name__)

MAX_SOURCE_TOKENS = 256
REPEAT_STOP = 4
"""Stop if the same token comes out this many times in a row (a degenerate loop)."""


class Session(Protocol):
    def run(self, output_names: Sequence[str] | None, feeds: dict[str, Any]) -> list[Any]: ...


class MarianTokenizer:
    def __init__(self, source_spm: Path, target_spm: Path, vocab: dict[str, int]) -> None:
        self._source = spm.SentencePieceProcessor(model_file=str(source_spm))
        self._target = spm.SentencePieceProcessor(model_file=str(target_spm))
        self._vocab = vocab
        self._pieces = {i: p for p, i in vocab.items()}
        self.unk_id = vocab["<unk>"]
        self.eos_id = vocab["</s>"]
        self.pad_id = vocab["<pad>"]
        self._special = {self.unk_id, self.eos_id, self.pad_id}

    def encode(self, text: str) -> list[int]:
        pieces: list[str] = self._source.encode(text, out_type=str)
        ids = [self._vocab.get(p, self.unk_id) for p in pieces][: MAX_SOURCE_TOKENS - 1]
        return [*ids, self.eos_id]

    def decode(self, ids: Sequence[int]) -> str:
        pieces = [self._pieces[i] for i in ids if i not in self._special and i in self._pieces]
        text: str = self._target.decode_pieces(pieces)
        return text.strip()


class MarianTranslator:
    def __init__(
        self,
        tokenizer: MarianTokenizer,
        encoder: Session,
        decoder: Session,
        *,
        decoder_start_id: int,
        max_new_tokens: int,
    ) -> None:
        self._tokenizer = tokenizer
        self._encoder = encoder
        self._decoder = decoder
        self._start = decoder_start_id
        self._max_new_tokens = max_new_tokens

    def translate(self, text: str) -> str:
        if not text.strip():
            return ""
        source = np.array([self._tokenizer.encode(text)], dtype=np.int64)
        mask = np.ones_like(source)
        hidden = self._encoder.run(None, {"input_ids": source, "attention_mask": mask})[0]

        output: list[int] = [self._start]
        for _ in range(self._max_new_tokens):
            logits: npt.NDArray[np.float32] = self._decoder.run(
                None,
                {
                    "input_ids": np.array([output], dtype=np.int64),
                    "encoder_hidden_states": hidden,
                    "encoder_attention_mask": mask,
                },
            )[0]
            scores = np.array(logits[0, -1], dtype=np.float32)
            scores[self._tokenizer.pad_id] = -np.inf
            token = int(scores.argmax())
            if token == self._tokenizer.eos_id:
                break
            output.append(token)
            if len(output) > REPEAT_STOP and len(set(output[-REPEAT_STOP:])) == 1:
                break
        return self._tokenizer.decode(output[1:])

    def close(self) -> None:
        self._encoder = self._decoder = _ClosedSession()


class _ClosedSession:
    def run(self, output_names: Sequence[str] | None, feeds: dict[str, Any]) -> list[Any]:
        raise RuntimeError("translator is closed")


def load_marian(model_dir: Path, config: TranslationConfig, *, threads: int) -> MarianTranslator:
    def path(name: str) -> Path:
        return model_dir / config.file(name)

    options = ort.SessionOptions()
    options.intra_op_num_threads = threads
    options.inter_op_num_threads = 1

    def session(name: str) -> Session:
        created: Session = ort.InferenceSession(
            str(path(name)), options, providers=["CPUExecutionProvider"]
        )
        return created

    model_config = json.loads(path("config.json").read_text(encoding="utf-8"))
    vocab = json.loads(path("vocab.json").read_text(encoding="utf-8"))
    tokenizer = MarianTokenizer(path("source.spm"), path("target.spm"), vocab)
    translator = MarianTranslator(
        tokenizer,
        session("encoder_model.onnx"),
        session("decoder_model.onnx"),
        decoder_start_id=int(model_config.get("decoder_start_token_id", tokenizer.pad_id)),
        max_new_tokens=config.max_new_tokens,
    )
    logger.info("Loaded translator from %s", model_dir)
    return translator

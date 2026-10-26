"""Sentence embeddings with ONNX Runtime and Hugging Face tokenizers (no PyTorch needed)."""

import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

import numpy as np
import numpy.typing as npt
import onnxruntime as ort
from tokenizers import Tokenizer

from rb_engine.domain.catalog import EmbeddingConfig
from rb_engine.ports.library import Vectors

logger = logging.getLogger(__name__)

PAD_TOKEN_CANDIDATES = ("<pad>", "[PAD]")


def pool(
    hidden: npt.NDArray[np.float32],
    attention_mask: npt.NDArray[np.int64],
    method: Literal["mean", "cls"],
) -> Vectors:
    """Pool token states (batch, tokens, dim) into L2-normalized vectors (batch, dim)."""
    if method == "cls":
        pooled = hidden[:, 0, :]
    else:
        mask = attention_mask[:, :, None].astype(np.float32)
        pooled = (hidden * mask).sum(axis=1) / np.clip(mask.sum(axis=1), 1e-9, None)
    norms = np.linalg.norm(pooled, axis=1, keepdims=True)
    return (pooled / np.clip(norms, 1e-12, None)).astype(np.float32)


class OnnxEmbedder:
    def __init__(
        self,
        model_dir: Path,
        config: EmbeddingConfig,
        *,
        threads: int,
        batch_size: int,
    ) -> None:
        self._config = config
        self._batch_size = batch_size
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        self._session: ort.InferenceSession | None = ort.InferenceSession(
            str(model_dir / config.onnx_file), options, providers=["CPUExecutionProvider"]
        )
        self._input_names = {i.name for i in self._session.get_inputs()}
        self._dimension = int(self._session.get_outputs()[0].shape[-1])

        self._tokenizer = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        self._tokenizer.enable_truncation(max_length=config.max_tokens)
        pad_token = next(
            (t for t in PAD_TOKEN_CANDIDATES if self._tokenizer.token_to_id(t) is not None), None
        )
        pad_id = self._tokenizer.token_to_id(pad_token) if pad_token else 0
        self._tokenizer.enable_padding(pad_id=pad_id, pad_token=pad_token or "[PAD]")
        logger.info("Loaded embedder %s (dim %d)", model_dir, self._dimension)

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_queries(self, texts: Sequence[str]) -> Vectors:
        return self._embed([self._config.query_prefix + t for t in texts])

    def embed_passages(self, texts: Sequence[str]) -> Vectors:
        return self._embed([self._config.passage_prefix + t for t in texts])

    def close(self) -> None:
        self._session = None  # releases the native session and its memory

    def _embed(self, texts: Sequence[str]) -> Vectors:
        if self._session is None:
            raise RuntimeError("embedder is closed")
        if not texts:
            return np.zeros((0, self._dimension), dtype=np.float32)
        batches = [
            self._embed_batch(self._session, texts[i : i + self._batch_size])
            for i in range(0, len(texts), self._batch_size)
        ]
        return np.concatenate(batches, axis=0)

    def _embed_batch(self, session: ort.InferenceSession, texts: Sequence[str]) -> Vectors:
        encodings = self._tokenizer.encode_batch(list(texts))
        input_ids = np.array([e.ids for e in encodings], dtype=np.int64)
        attention_mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)
        feeds = {"input_ids": input_ids, "attention_mask": attention_mask}
        if "token_type_ids" in self._input_names:
            feeds["token_type_ids"] = np.zeros_like(input_ids)
        hidden = session.run(None, feeds)[0]
        return pool(np.asarray(hidden, dtype=np.float32), attention_mask, self._config.pooling)

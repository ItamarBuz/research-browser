"""Pooling math always runs; the real-model test runs only where a model is available.

Set RB_TEST_EMBEDDER_DIR to a downloaded multilingual E5 model directory (the folder holding
onnx/ and tokenizer.json) to run it.
"""

import os
from pathlib import Path

import numpy as np
import pytest

from rb_engine.adapters.embed.onnx_embedder import OnnxEmbedder, pool
from rb_engine.domain.catalog import EmbeddingConfig


def test_mean_pooling_ignores_padding() -> None:
    hidden = np.array([[[1.0, 0.0], [3.0, 0.0], [100.0, 100.0]]], dtype=np.float32)
    mask = np.array([[1, 1, 0]], dtype=np.int64)
    np.testing.assert_allclose(pool(hidden, mask, "mean"), [[1.0, 0.0]])


def test_cls_pooling_takes_first_token_and_normalizes() -> None:
    hidden = np.array([[[3.0, 4.0], [9.0, 9.0]]], dtype=np.float32)
    mask = np.array([[1, 1]], dtype=np.int64)
    np.testing.assert_allclose(pool(hidden, mask, "cls"), [[0.6, 0.8]], rtol=1e-6)


MODEL_DIR = os.environ.get("RB_TEST_EMBEDDER_DIR")


@pytest.mark.skipif(not MODEL_DIR, reason="RB_TEST_EMBEDDER_DIR not set")
def test_real_model_matches_across_languages() -> None:
    assert MODEL_DIR is not None
    config = EmbeddingConfig(
        onnx_file="onnx/model_quantized.onnx",
        pooling="mean",
        query_prefix="query: ",
        passage_prefix="passage: ",
    )
    embedder = OnnxEmbedder(Path(MODEL_DIR), config, threads=2, batch_size=4)
    query = embedder.embed_queries(["האם שינה משפרת את הזיכרון?"])[0]  # does sleep improve memory?
    passages = embedder.embed_passages(
        [
            "Participants who slept after learning recalled more word pairs.",
            "Rising temperatures reduce wheat and maize yields.",
        ]
    )
    assert passages.shape == (2, embedder.dimension)
    np.testing.assert_allclose(np.linalg.norm(passages, axis=1), 1.0, rtol=1e-5)
    related, unrelated = passages @ query
    assert related > unrelated + 0.05

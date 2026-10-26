"""A deterministic stand-in for the ONNX embedder: hashed bag-of-words vectors.

Texts sharing words get similar vectors, which is enough to test ranking, filtering and
index bookkeeping without downloading a model.
"""

import hashlib
import re
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager

import numpy as np

from rb_engine.domain.errors import ModelNotReadyError
from rb_engine.ports.library import Embedder, Vectors

DIMENSION = 64
_WORD = re.compile(r"\w+")


class FakeEmbedder:
    dimension = DIMENSION

    def _vector(self, text: str) -> np.ndarray:
        vector = np.zeros(DIMENSION, dtype=np.float32)
        for word in _WORD.findall(text.lower()):
            bucket = int(hashlib.md5(word.encode()).hexdigest(), 16) % DIMENSION
            vector[bucket] += 1.0
        norm = np.linalg.norm(vector)
        return vector / norm if norm else vector

    def embed_queries(self, texts: Sequence[str]) -> Vectors:
        return np.stack([self._vector(t) for t in texts]) if texts else np.zeros((0, DIMENSION))

    def embed_passages(self, texts: Sequence[str]) -> Vectors:
        return self.embed_queries(texts)


class FakeEmbedderResolver:
    def __init__(self, *, ready: bool = True, model_id: str = "embed-test") -> None:
        self.ready = ready
        self.model_id = model_id
        self.leases = 0

    def active_model_id(self) -> str:
        return self.model_id

    def known_model_ids(self) -> list[str]:
        return ["embed-test", "embed-other"]

    def is_ready(self) -> bool:
        return self.ready

    @asynccontextmanager
    async def lease(self) -> AsyncIterator[Embedder]:
        if not self.ready:
            raise ModelNotReadyError("The semantic search model is not downloaded yet.")
        self.leases += 1
        yield FakeEmbedder()

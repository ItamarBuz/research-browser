"""Ports for parsing, embedding and indexing library documents."""

from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import numpy as np
import numpy.typing as npt

from rb_engine.text.language import SourceLanguage

Vectors = npt.NDArray[np.float32]


@dataclass(frozen=True, slots=True)
class SizedLine:
    text: str
    size: float
    """Largest font size in the line, in PDF units."""


@dataclass(frozen=True, slots=True)
class RawPdf:
    pages: list[str]
    """Raw extracted text per page, exactly as the PDF library returns it."""
    info: dict[str, str]
    """PDF document-info metadata (Title, Author, CreationDate, ...)."""
    first_page_lines: list[SizedLine] = field(default_factory=list)
    """Page 1 lines with font sizes, in reading order (the title is set in the largest font)."""


class PdfParser(Protocol):
    def extract(self, path: Path) -> RawPdf: ...


class Embedder(Protocol):
    """Turns text into L2-normalized vectors. Queries and passages may be encoded differently."""

    @property
    def dimension(self) -> int: ...

    def embed_queries(self, texts: Sequence[str]) -> Vectors: ...

    def embed_passages(self, texts: Sequence[str]) -> Vectors: ...


class EmbedderResolver(Protocol):
    """The embedding model for the current tier, loaded on demand."""

    def active_model_id(self) -> str: ...

    def known_model_ids(self) -> list[str]:
        """Every embedder that could have an index on disk."""
        ...

    def is_ready(self) -> bool: ...

    def lease(self) -> AbstractAsyncContextManager[Embedder]:
        """Raises ModelNotReadyError when the model is not downloaded."""
        ...


@dataclass(frozen=True, slots=True)
class IndexedPassage:
    passage_id: str
    document_id: str
    language: SourceLanguage
    """The document's language, used by the source-language filter."""
    search_text: str
    vector: npt.NDArray[np.float32]


@dataclass(frozen=True, slots=True)
class IndexHit:
    passage_id: str
    document_id: str
    score: float
    similarity: float


class PassageIndex(Protocol):
    """Hybrid (vector + keyword) index over passages for one embedding model."""

    def add(self, passages: Sequence[IndexedPassage]) -> None: ...

    def delete_document(self, document_id: str) -> None: ...

    def document_ids(self) -> set[str]: ...

    def search(
        self,
        vector: npt.NDArray[np.float32],
        text: str,
        language: SourceLanguage | None,
        limit: int,
    ) -> list[IndexHit]: ...


class PassageIndexStore(Protocol):
    def open(self, model_id: str, dimension: int | None = None) -> PassageIndex | None:
        """The index for `model_id`; created if missing and `dimension` is given, else None."""
        ...

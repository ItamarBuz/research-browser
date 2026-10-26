"""Catalog of downloadable local AI models."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from rb_engine.domain.hardware import Tier

ALLOWED_LICENSES = frozenset({"apache-2.0", "mit", "bsd-2-clause", "bsd-3-clause"})
"""Permissive licenses only, so the app can be redistributed and used for any purpose."""

HF_BASE_URL = "https://huggingface.co"


class ModelRole(StrEnum):
    EMBEDDER = "embedder"
    RERANKER = "reranker"
    NLI = "nli"
    LLM = "llm"


class EmbeddingConfig(BaseModel):
    """How to run an embedding model; models differ in pooling and expected prefixes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    onnx_file: str
    pooling: Literal["mean", "cls"]
    query_prefix: str = ""
    passage_prefix: str = ""
    max_tokens: int = Field(default=512, ge=16, le=8192)


class ModelFile(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(gt=0)


class ModelSpec(BaseModel):
    """One catalog entry, pinned to an exact repository revision and file hashes."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str
    role: ModelRole
    tiers: tuple[Tier, ...] = Field(
        description="Tiers this model is recommended for; empty means optional everywhere"
    )
    repo: str
    revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    license: str
    files: tuple[ModelFile, ...] = Field(min_length=1)
    embedding: EmbeddingConfig | None = None

    @property
    def size_bytes(self) -> int:
        return sum(f.size_bytes for f in self.files)

    def download_url(self, file: ModelFile) -> str:
        return f"{HF_BASE_URL}/{self.repo}/resolve/{self.revision}/{file.path}"

"""Loads and validates the model catalog (hand-edited spec + generated lockfile)."""

import json
import tomllib
from collections.abc import Iterable, Mapping
from importlib import resources

from pydantic import BaseModel, ConfigDict, Field, model_validator

from rb_engine.domain.catalog import (
    ALLOWED_LICENSES,
    TRANSLATION_FILES,
    TRANSLATOR_ROLES,
    EmbeddingConfig,
    ModelFile,
    ModelRole,
    ModelSpec,
    TranslationConfig,
)
from rb_engine.domain.errors import ModelNotFoundError
from rb_engine.domain.hardware import Tier

SPEC_RESOURCE = "models.toml"
LOCK_RESOURCE = "models.lock.json"


class CatalogError(ValueError):
    """The bundled catalog is inconsistent. This is a packaging bug, not a user error."""


class SpecEntry(BaseModel):
    """An entry as written by hand in models.toml."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    name: str
    role: ModelRole
    tiers: tuple[Tier, ...]
    repo: str
    license: str
    license_source: str | None = None
    files: tuple[str, ...] = Field(min_length=1)
    embedding: EmbeddingConfig | None = None
    translation: TranslationConfig | None = None

    @model_validator(mode="after")
    def _embedders_need_config(self) -> "SpecEntry":
        if (self.role == ModelRole.EMBEDDER) != (self.embedding is not None):
            raise ValueError(f"{self.id}: embedders (and only embedders) need [embedding]")
        if self.embedding and self.embedding.onnx_file not in self.files:
            raise ValueError(f"{self.id}: embedding.onnx_file must be listed in files")
        if (self.role in TRANSLATOR_ROLES) != (self.translation is not None):
            raise ValueError(f"{self.id}: translators (and only translators) need [translation]")
        if self.translation:
            missing = [
                f for f in map(self.translation.file, TRANSLATION_FILES) if f not in self.files
            ]
            if missing:
                raise ValueError(f"{self.id}: translation files missing from files: {missing}")
        return self


class LockedFile(BaseModel):
    sha256: str
    size_bytes: int


class LockedEntry(BaseModel):
    """What scripts/pin_models.py records for an entry."""

    revision: str
    files: dict[str, LockedFile]


def parse_spec(toml_text: str) -> list[SpecEntry]:
    data = tomllib.loads(toml_text)
    return [SpecEntry.model_validate(raw) for raw in data.get("models", [])]


def parse_lock(json_text: str) -> dict[str, LockedEntry]:
    raw: dict[str, object] = json.loads(json_text)
    return {model_id: LockedEntry.model_validate(entry) for model_id, entry in raw.items()}


class ModelCatalog:
    def __init__(self, models: Iterable[ModelSpec]) -> None:
        self._models: dict[str, ModelSpec] = {}
        for model in models:
            if model.id in self._models:
                raise CatalogError(f"duplicate model id {model.id!r}")
            self._models[model.id] = model
        self._check_one_per_role_per_tier()

    def _check_one_per_role_per_tier(self) -> None:
        seen: dict[tuple[Tier, ModelRole], str] = {}
        for model in self._models.values():
            for tier in model.tiers:
                key = (tier, model.role)
                if key in seen:
                    raise CatalogError(
                        f"{model.id!r} and {seen[key]!r} are both the {model.role} for {tier}"
                    )
                seen[key] = model.id

    def all(self) -> list[ModelSpec]:
        return list(self._models.values())

    def get(self, model_id: str) -> ModelSpec:
        try:
            return self._models[model_id]
        except KeyError:
            raise ModelNotFoundError(f"No model with id {model_id!r}") from None

    def recommended_for(self, tier: Tier) -> list[ModelSpec]:
        return [m for m in self._models.values() if tier in m.tiers]


def build_catalog(spec: Iterable[SpecEntry], lock: Mapping[str, LockedEntry]) -> ModelCatalog:
    models: list[ModelSpec] = []
    for entry in spec:
        if entry.license not in ALLOWED_LICENSES:
            raise CatalogError(f"{entry.id!r} has non-permissive license {entry.license!r}")
        locked = lock.get(entry.id)
        if locked is None:
            raise CatalogError(f"{entry.id!r} is not pinned; run scripts/pin_models.py")
        missing = set(entry.files) - set(locked.files)
        if missing:
            raise CatalogError(f"{entry.id!r} lock is missing files {sorted(missing)}")
        models.append(
            ModelSpec(
                id=entry.id,
                name=entry.name,
                role=entry.role,
                tiers=entry.tiers,
                repo=entry.repo,
                revision=locked.revision,
                license=entry.license,
                embedding=entry.embedding,
                translation=entry.translation,
                files=tuple(
                    ModelFile(
                        path=path,
                        sha256=locked.files[path].sha256,
                        size_bytes=locked.files[path].size_bytes,
                    )
                    for path in entry.files
                ),
            )
        )
    return ModelCatalog(models)


def load_bundled_catalog() -> ModelCatalog:
    package = resources.files("rb_engine.catalog")
    spec = parse_spec(package.joinpath(SPEC_RESOURCE).read_text(encoding="utf-8"))
    lock = parse_lock(package.joinpath(LOCK_RESOURCE).read_text(encoding="utf-8"))
    return build_catalog(spec, lock)

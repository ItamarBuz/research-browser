"""Resolves the active tier's embedding model and leases it through the residency manager."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from rb_engine.adapters.embed.onnx_embedder import OnnxEmbedder
from rb_engine.domain.catalog import ModelRole, ModelSpec
from rb_engine.domain.errors import ModelNotReadyError
from rb_engine.domain.hardware import HardwareProfile, Tier
from rb_engine.ports.library import Embedder
from rb_engine.runtime.catalog import ModelCatalog
from rb_engine.runtime.model_manager import ModelManager
from rb_engine.runtime.residency import ResidencyManager

BATCH_SIZES: dict[Tier, int] = {Tier.LITE: 8, Tier.STANDARD: 16, Tier.PRO: 32}


class CatalogEmbedderResolver:
    def __init__(
        self,
        catalog: ModelCatalog,
        models: ModelManager,
        residency: ResidencyManager,
        hardware: HardwareProfile,
        current_tier: Callable[[], Tier],
    ) -> None:
        self._catalog = catalog
        self._models = models
        self._residency = residency
        self._hardware = hardware
        self._current_tier = current_tier

    def _active_spec(self) -> ModelSpec:
        tier = self._current_tier()
        for spec in self._catalog.recommended_for(tier):
            if spec.role == ModelRole.EMBEDDER:
                return spec
        raise ModelNotReadyError(f"No embedding model is configured for the {tier} tier")

    def active_model_id(self) -> str:
        return self._active_spec().id

    def known_model_ids(self) -> list[str]:
        return [m.id for m in self._catalog.all() if m.role == ModelRole.EMBEDDER]

    def is_ready(self) -> bool:
        return self._models.state(self.active_model_id()).status == "ready"

    @asynccontextmanager
    async def lease(self) -> AsyncIterator[Embedder]:
        spec = self._active_spec()
        if not self.is_ready():
            raise ModelNotReadyError(
                f"The semantic search model ({spec.name}) is not downloaded yet. "
                "Download it in Settings."
            )
        config = spec.embedding
        if config is None:
            raise ModelNotReadyError(f"{spec.name} has no embedding configuration")
        model_dir = self._models.path_of(spec.id)
        batch_size = BATCH_SIZES[self._current_tier()]
        threads = max(1, self._hardware.cpu_physical_cores)

        def load() -> OnnxEmbedder:
            return OnnxEmbedder(model_dir, config, threads=threads, batch_size=batch_size)

        async with self._residency.lease(f"embedder:{spec.id}", load) as embedder:
            yield embedder

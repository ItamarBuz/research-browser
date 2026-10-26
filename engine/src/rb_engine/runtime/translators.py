"""Translates queries between Hebrew and English with the downloaded OPUS-MT models.

Translation is an enhancement: when a model is not downloaded, callers get None and search
with the original query instead of failing.
"""

import asyncio
import logging
from collections.abc import Callable

from rb_engine.adapters.translate.marian_onnx import MarianTranslator, load_marian
from rb_engine.domain.catalog import ModelRole
from rb_engine.domain.hardware import HardwareProfile
from rb_engine.runtime.catalog import ModelCatalog
from rb_engine.runtime.model_manager import ModelManager
from rb_engine.runtime.residency import ResidencyManager

logger = logging.getLogger(__name__)

ROLE_FOR_DIRECTION = {
    ("he", "en"): ModelRole.TRANSLATOR_HE_EN,
    ("en", "he"): ModelRole.TRANSLATOR_EN_HE,
}


class CatalogTranslator:
    def __init__(
        self,
        catalog: ModelCatalog,
        models: ModelManager,
        residency: ResidencyManager,
        hardware: HardwareProfile,
    ) -> None:
        self._catalog = catalog
        self._models = models
        self._residency = residency
        self._threads = max(1, hardware.cpu_physical_cores)
        self._memo: dict[tuple[str, str, str], str] = {}

    def is_available(self, source: str, target: str) -> bool:
        role = ROLE_FOR_DIRECTION.get((source, target))
        return any(
            m.role == role and self._models.state(m.id).status == "ready"
            for m in self._catalog.all()
        )

    async def translate(self, text: str, source: str, target: str) -> str | None:
        key = (text, source, target)
        if key in self._memo:
            return self._memo[key]
        role = ROLE_FOR_DIRECTION.get((source, target))
        spec = next(
            (
                m
                for m in self._catalog.all()
                if m.role == role and self._models.state(m.id).status == "ready"
            ),
            None,
        )
        if spec is None or spec.translation is None:
            return None
        model_dir = self._models.path_of(spec.id)
        config = spec.translation
        load: Callable[[], MarianTranslator] = lambda: load_marian(  # noqa: E731
            model_dir, config, threads=self._threads
        )
        try:
            async with self._residency.lease(f"translator:{spec.id}", load) as translator:
                result = await asyncio.to_thread(translator.translate, text)
        except Exception:
            logger.exception("Translating with %s failed", spec.id)
            return None
        self._memo[key] = result
        return result

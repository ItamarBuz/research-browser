"""Composition root: builds the engine's long-lived services once at startup."""

import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass

import httpx

from rb_engine.adapters.pdf.pdfium_parser import PdfiumParser
from rb_engine.adapters.sources.arxiv import ArxivSource
from rb_engine.adapters.sources.europe_pmc import EuropePmcSource
from rb_engine.adapters.sources.http import CachedSourceHttp, HttpCache
from rb_engine.adapters.sources.openalex import OpenAlexSource
from rb_engine.adapters.sources.semantic_scholar import SemanticScholarSource
from rb_engine.adapters.store.lancedb_index import LanceIndexStore
from rb_engine.adapters.store.library_repository import LibraryRepository
from rb_engine.domain.hardware import HardwareProfile, Tier, TierDecision
from rb_engine.ports.library import EmbedderResolver
from rb_engine.ports.sources import AcademicSource
from rb_engine.runtime.catalog import ModelCatalog, load_bundled_catalog
from rb_engine.runtime.embedders import CatalogEmbedderResolver
from rb_engine.runtime.hardware import detect_hardware
from rb_engine.runtime.model_manager import ModelManager
from rb_engine.runtime.online import OnlineConfig
from rb_engine.runtime.paths import DataPaths
from rb_engine.runtime.preferences import PreferencesStore
from rb_engine.runtime.residency import RESIDENT_LIMITS, ResidencyManager
from rb_engine.runtime.secrets import KeyringSecretStore, SecretStore
from rb_engine.runtime.tier_policy import decide_tier
from rb_engine.runtime.translators import CatalogTranslator
from rb_engine.services.discovery import DiscoveryService, Translator
from rb_engine.services.library import LibraryService

logger = logging.getLogger(__name__)

TIER_ENV_VAR = "RB_TIER"


def read_env_tier() -> Tier | None:
    raw = os.environ.get(TIER_ENV_VAR)
    if not raw:
        return None
    try:
        return Tier(raw.lower())
    except ValueError:
        logger.warning("Ignoring invalid %s=%r (expected lite, standard or pro)", TIER_ENV_VAR, raw)
        return None


@dataclass
class EngineServices:
    paths: DataPaths
    hardware: HardwareProfile
    preferences: PreferencesStore
    catalog: ModelCatalog
    models: ModelManager
    residency: ResidencyManager
    library: LibraryService
    online: OnlineConfig
    discovery: DiscoveryService
    source_http: CachedSourceHttp
    http_cache: HttpCache
    env_tier: Tier | None

    def tier_decision(self) -> TierDecision:
        return decide_tier(
            self.hardware,
            user_override=self.preferences.load().tier_override,
            env_override=self.env_tier,
        )

    async def start(self) -> None:
        await self.library.start()

    async def stop(self) -> None:
        await self.library.stop()
        await self.source_http.aclose()


def build_services(
    paths: DataPaths,
    *,
    hardware: HardwareProfile | None = None,
    catalog: ModelCatalog | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    env_tier: Tier | None = None,
    embedders: EmbedderResolver | None = None,
    secrets: SecretStore | None = None,
    sources: Sequence[AcademicSource] | None = None,
    translator: Translator | None = None,
) -> EngineServices:
    paths.ensure()
    hardware = hardware or detect_hardware()
    catalog = catalog or load_bundled_catalog()
    preferences = PreferencesStore(paths.preferences)

    def current_tier() -> Tier:
        user = preferences.load().tier_override
        return decide_tier(hardware, user_override=user, env_override=env_tier).effective

    tier = current_tier()
    logger.info("Effective hardware tier: %s", tier)
    models = ModelManager(catalog, paths.models, transport=transport)
    residency = ResidencyManager(RESIDENT_LIMITS[tier])
    embedders = embedders or CatalogEmbedderResolver(
        catalog, models, residency, hardware, current_tier
    )
    library = LibraryService(
        LibraryRepository(paths.library_db),
        paths.library_files,
        PdfiumParser(),
        embedders,
        LanceIndexStore(paths.library_index),
    )
    online = OnlineConfig(preferences, secrets or KeyringSecretStore())
    http_cache = HttpCache(paths.http_cache)
    source_http = CachedSourceHttp(http_cache)
    sources = sources or [
        OpenAlexSource(source_http, online.credentials),
        SemanticScholarSource(source_http, online.credentials),
        ArxivSource(source_http),
        EuropePmcSource(source_http),
    ]
    discovery = DiscoveryService(
        sources,
        translator or CatalogTranslator(catalog, models, residency, hardware),
        embedders,
        online.enabled_sources,
        library.known_dois,
    )
    return EngineServices(
        paths=paths,
        hardware=hardware,
        preferences=preferences,
        catalog=catalog,
        models=models,
        residency=residency,
        library=library,
        online=online,
        discovery=discovery,
        source_http=source_http,
        http_cache=http_cache,
        env_tier=env_tier,
    )

"""Composition root: builds the engine's long-lived services once at startup."""

import logging
import os
from dataclasses import dataclass

import httpx

from rb_engine.domain.hardware import HardwareProfile, Tier, TierDecision
from rb_engine.runtime.catalog import ModelCatalog, load_bundled_catalog
from rb_engine.runtime.hardware import detect_hardware
from rb_engine.runtime.model_manager import ModelManager
from rb_engine.runtime.paths import DataPaths
from rb_engine.runtime.preferences import PreferencesStore
from rb_engine.runtime.residency import RESIDENT_LIMITS, ResidencyManager
from rb_engine.runtime.tier_policy import decide_tier

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
    hardware: HardwareProfile
    preferences: PreferencesStore
    catalog: ModelCatalog
    models: ModelManager
    residency: ResidencyManager
    env_tier: Tier | None

    def tier_decision(self) -> TierDecision:
        return decide_tier(
            self.hardware,
            user_override=self.preferences.load().tier_override,
            env_override=self.env_tier,
        )


def build_services(
    paths: DataPaths,
    *,
    hardware: HardwareProfile | None = None,
    catalog: ModelCatalog | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    env_tier: Tier | None = None,
) -> EngineServices:
    paths.ensure()
    hardware = hardware or detect_hardware()
    catalog = catalog or load_bundled_catalog()
    preferences = PreferencesStore(paths.preferences)
    decision = decide_tier(
        hardware, user_override=preferences.load().tier_override, env_override=env_tier
    )
    logger.info("Hardware tier: detected %s, effective %s", decision.detected, decision.effective)
    return EngineServices(
        hardware=hardware,
        preferences=preferences,
        catalog=catalog,
        models=ModelManager(catalog, paths.models, transport=transport),
        residency=ResidencyManager(RESIDENT_LIMITS[decision.effective]),
        env_tier=env_tier,
    )

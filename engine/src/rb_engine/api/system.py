"""Hardware profile and performance-tier endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from rb_engine.api.deps import Services
from rb_engine.domain.hardware import HardwareProfile, Tier, TierDecision
from rb_engine.runtime.container import EngineServices
from rb_engine.runtime.residency import RESIDENT_LIMITS

router = APIRouter(prefix="/system", tags=["system"])


class SystemInfo(BaseModel):
    hardware: HardwareProfile
    tier: TierDecision
    resident_model_limit: int


class TierOverrideRequest(BaseModel):
    tier: Tier | None = Field(description="null returns to automatic detection")


def _system_info(services: EngineServices) -> SystemInfo:
    decision = services.tier_decision()
    return SystemInfo(
        hardware=services.hardware,
        tier=decision,
        resident_model_limit=RESIDENT_LIMITS[decision.effective],
    )


@router.get("", operation_id="getSystem")
def get_system(services: Services) -> SystemInfo:
    return _system_info(services)


@router.put("/tier-override", operation_id="setTierOverride")
async def set_tier_override(body: TierOverrideRequest, services: Services) -> SystemInfo:
    current = services.preferences.load()
    services.preferences.save(current.model_copy(update={"tier_override": body.tier}))
    info = _system_info(services)
    await services.residency.set_limit(info.resident_model_limit)
    return info

"""Model catalog and download endpoints."""

from fastapi import APIRouter, status
from pydantic import BaseModel

from rb_engine.api.deps import Services
from rb_engine.domain.catalog import ModelRole, ModelSpec
from rb_engine.domain.hardware import Tier
from rb_engine.runtime.container import EngineServices
from rb_engine.runtime.model_manager import ModelState

router = APIRouter(prefix="/models", tags=["models"])


class ModelInfo(BaseModel):
    id: str
    name: str
    role: ModelRole
    license: str
    size_bytes: int
    tiers: list[Tier]
    recommended: bool
    state: ModelState


class ModelList(BaseModel):
    tier: Tier
    models: list[ModelInfo]
    """Models recommended for `tier` come first."""


def _info(services: EngineServices, spec: ModelSpec, tier: Tier) -> ModelInfo:
    return ModelInfo(
        id=spec.id,
        name=spec.name,
        role=spec.role,
        license=spec.license,
        size_bytes=spec.size_bytes,
        tiers=list(spec.tiers),
        recommended=tier in spec.tiers,
        state=services.models.state(spec.id),
    )


@router.get("", operation_id="listModels")
def list_models(services: Services) -> ModelList:
    tier = services.tier_decision().effective
    infos = [_info(services, spec, tier) for spec in services.catalog.all()]
    infos.sort(key=lambda m: not m.recommended)  # stable: keeps catalog order within groups
    return ModelList(tier=tier, models=infos)


@router.post(
    "/{model_id}/download",
    operation_id="startModelDownload",
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_model_download(model_id: str, services: Services) -> ModelInfo:
    spec = services.catalog.get(model_id)
    services.models.start_download(model_id)
    return _info(services, spec, services.tier_decision().effective)

"""Host hardware description and the performance tiers derived from it."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class Tier(StrEnum):
    """Feature/model scale the engine runs at. Ordered from smallest to largest."""

    LITE = "lite"
    STANDARD = "standard"
    PRO = "pro"


GpuBackend = Literal["cuda", "metal"]


class GpuInfo(BaseModel):
    name: str
    backend: GpuBackend
    memory_mb: int = Field(
        ge=0, description="Dedicated VRAM, or the usable share of unified memory"
    )
    unified_memory: bool = Field(description="True when the GPU shares system RAM (Apple Silicon)")


class HardwareProfile(BaseModel):
    os: str
    arch: str
    cpu_physical_cores: int = Field(ge=1)
    cpu_logical_cores: int = Field(ge=1)
    total_ram_mb: int = Field(ge=0)
    available_ram_mb: int = Field(ge=0)
    gpus: list[GpuInfo]


TierReasonCode = Literal[
    "system_ram",
    "gpu_memory",
    "unified_memory",
    "override_user",
    "override_env",
]


class TierReason(BaseModel):
    """A machine-readable reason; the UI turns it into a localized sentence."""

    code: TierReasonCode
    value_gb: float | None = None


class TierDecision(BaseModel):
    detected: Tier
    effective: Tier
    override_source: Literal["user", "env"] | None
    reasons: list[TierReason]

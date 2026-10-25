import pytest

from rb_engine.domain.hardware import GpuInfo, Tier
from rb_engine.runtime.tier_policy import decide_tier, detect_tier
from tests.fakes import hardware, nvidia

APPLE_16 = GpuInfo(name="Apple", backend="metal", memory_mb=10900, unified_memory=True)


@pytest.mark.parametrize(
    ("ram_gb", "gpus", "expected", "first_reason"),
    [
        (8, [], Tier.LITE, "system_ram"),
        (4, [], Tier.LITE, "system_ram"),
        (12, [], Tier.STANDARD, "system_ram"),
        (16, [], Tier.STANDARD, "system_ram"),
        (24, [], Tier.PRO, "system_ram"),
        (64, [], Tier.PRO, "system_ram"),
        # A modest GPU lifts an 8 GB machine to Standard...
        (8, [nvidia(6)], Tier.STANDARD, "gpu_memory"),
        # ...but not a machine with too little RAM for the rest of the pipeline.
        (6, [nvidia(8)], Tier.LITE, "system_ram"),
        (16, [nvidia(12)], Tier.PRO, "gpu_memory"),
        (8, [nvidia(12)], Tier.STANDARD, "gpu_memory"),
        # The best of several GPUs counts.
        (16, [nvidia(4), nvidia(16)], Tier.PRO, "gpu_memory"),
        # Unified memory: RAM alone decides, even though the GPU share looks large.
        (16, [APPLE_16], Tier.STANDARD, "unified_memory"),
    ],
)
def test_detect_tier(ram_gb: float, gpus: list[GpuInfo], expected: Tier, first_reason: str) -> None:
    tier, reasons = detect_tier(hardware(ram_gb=ram_gb, gpus=gpus))
    assert tier == expected
    assert reasons[0].code == first_reason


def test_reasons_carry_measured_values() -> None:
    _, reasons = detect_tier(hardware(ram_gb=8, gpus=[nvidia(6)]))
    assert [(r.code, r.value_gb) for r in reasons] == [("gpu_memory", 6.0), ("system_ram", 7.7)]


def test_no_override_uses_detection() -> None:
    decision = decide_tier(hardware(ram_gb=8))
    assert decision.detected == decision.effective == Tier.LITE
    assert decision.override_source is None


def test_user_override() -> None:
    decision = decide_tier(hardware(ram_gb=8), user_override=Tier.PRO)
    assert decision.detected == Tier.LITE
    assert decision.effective == Tier.PRO
    assert decision.override_source == "user"
    assert decision.reasons[0].code == "override_user"


def test_env_override_beats_user_override() -> None:
    decision = decide_tier(hardware(ram_gb=32), user_override=Tier.STANDARD, env_override=Tier.LITE)
    assert decision.effective == Tier.LITE
    assert decision.override_source == "env"

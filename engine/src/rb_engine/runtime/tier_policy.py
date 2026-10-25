"""Maps a hardware profile to a performance tier.

Thresholds sit slightly below the marketed sizes because the OS reports less than the
nominal amount (a "16 GB" laptop typically shows ~15.7 GB, an "8 GB" GPU 8192 MB).
"""

from rb_engine.domain.hardware import HardwareProfile, Tier, TierDecision, TierReason

# System RAM alone (CPU inference)
RAM_PRO_GB = 23.0  # nominal 24 GB
RAM_STANDARD_GB = 11.5  # nominal 12 GB

# Dedicated GPU memory, which also needs enough system RAM for everything else
VRAM_PRO_GB = 9.5  # nominal 10 GB
VRAM_STANDARD_GB = 3.5  # nominal 4 GB
RAM_FLOOR_FOR_GPU_PRO_GB = 15.5  # nominal 16 GB
RAM_FLOOR_FOR_GPU_STANDARD_GB = 7.5  # nominal 8 GB


def _gb(mb: int) -> float:
    return round(mb / 1024, 1)


def detect_tier(profile: HardwareProfile) -> tuple[Tier, list[TierReason]]:
    ram_gb = _gb(profile.total_ram_mb)
    unified = any(gpu.unified_memory for gpu in profile.gpus)
    # With unified memory the GPU competes with everything else for the same RAM, so the
    # RAM thresholds alone decide; acceleration then makes that tier fast.
    ram_reason = TierReason(code="unified_memory" if unified else "system_ram", value_gb=ram_gb)

    dedicated = [gpu for gpu in profile.gpus if not gpu.unified_memory]
    vram_gb = _gb(max((gpu.memory_mb for gpu in dedicated), default=0))
    gpu_reason = TierReason(code="gpu_memory", value_gb=vram_gb)

    if ram_gb >= RAM_PRO_GB:
        return Tier.PRO, [ram_reason]
    if vram_gb >= VRAM_PRO_GB and ram_gb >= RAM_FLOOR_FOR_GPU_PRO_GB:
        return Tier.PRO, [gpu_reason, ram_reason]
    if ram_gb >= RAM_STANDARD_GB:
        return Tier.STANDARD, [ram_reason]
    if vram_gb >= VRAM_STANDARD_GB and ram_gb >= RAM_FLOOR_FOR_GPU_STANDARD_GB:
        return Tier.STANDARD, [gpu_reason, ram_reason]
    return Tier.LITE, [ram_reason]


def decide_tier(
    profile: HardwareProfile,
    *,
    user_override: Tier | None = None,
    env_override: Tier | None = None,
) -> TierDecision:
    """The environment override (for testing) beats the user's choice, which beats detection."""
    detected, reasons = detect_tier(profile)
    if env_override is not None:
        return TierDecision(
            detected=detected,
            effective=env_override,
            override_source="env",
            reasons=[TierReason(code="override_env"), *reasons],
        )
    if user_override is not None:
        return TierDecision(
            detected=detected,
            effective=user_override,
            override_source="user",
            reasons=[TierReason(code="override_user"), *reasons],
        )
    return TierDecision(
        detected=detected, effective=detected, override_source=None, reasons=reasons
    )

from collections.abc import Sequence

from rb_engine.runtime.hardware import NVIDIA_SMI_QUERY, detect_hardware, parse_nvidia_smi


def test_parses_multiple_gpus() -> None:
    gpus = parse_nvidia_smi("NVIDIA GeForce RTX 3060, 12288\nNVIDIA RTX A2000, 6144\n")
    assert [(g.name, g.memory_mb, g.backend) for g in gpus] == [
        ("NVIDIA GeForce RTX 3060", 12288, "cuda"),
        ("NVIDIA RTX A2000", 6144, "cuda"),
    ]


def test_skips_unparseable_lines() -> None:
    gpus = parse_nvidia_smi("garbage\nTesla T4, [N/A]\nTesla T4, 15360\n")
    assert [g.memory_mb for g in gpus] == [15360]


def test_detects_nvidia_through_runner() -> None:
    calls: list[Sequence[str]] = []

    def runner(args: Sequence[str]) -> str | None:
        calls.append(args)
        return "NVIDIA GeForce RTX 4090, 24564\n"

    profile = detect_hardware(run=runner, system="Windows", machine="AMD64")

    assert calls == [NVIDIA_SMI_QUERY]
    assert profile.gpus[0].memory_mb == 24564
    assert profile.cpu_logical_cores >= profile.cpu_physical_cores >= 1
    assert profile.total_ram_mb >= profile.available_ram_mb > 0


def test_no_gpu_when_probe_unavailable() -> None:
    profile = detect_hardware(run=lambda _args: None, system="Linux", machine="x86_64")
    assert profile.gpus == []


def test_apple_silicon_uses_unified_memory_without_probing() -> None:
    def runner(_args: Sequence[str]) -> str | None:
        raise AssertionError("nvidia-smi must not be called on Apple Silicon")

    profile = detect_hardware(run=runner, system="Darwin", machine="arm64")

    (gpu,) = profile.gpus
    assert gpu.backend == "metal"
    assert gpu.unified_memory
    assert 0 < gpu.memory_mb < profile.total_ram_mb

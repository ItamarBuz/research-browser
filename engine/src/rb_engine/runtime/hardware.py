"""Detects CPU, memory and GPU acceleration on the host.

GPU detection covers the two backends local inference uses in practice today: NVIDIA CUDA
(via `nvidia-smi`, which ships with the driver) and Apple Silicon Metal. AMD/Intel GPUs are
not detected yet; those machines are tiered by system RAM, which is the safe direction.
"""

import logging
import platform
import subprocess
from collections.abc import Callable, Sequence

import psutil

from rb_engine.domain.hardware import GpuInfo, HardwareProfile

logger = logging.getLogger(__name__)

CommandRunner = Callable[[Sequence[str]], str | None]

NVIDIA_SMI_QUERY = (
    "nvidia-smi",
    "--query-gpu=name,memory.total",
    "--format=csv,noheader,nounits",
)
COMMAND_TIMEOUT_S = 5.0

APPLE_GPU_SHARE = 2 / 3
"""macOS lets the GPU wire roughly two thirds of unified memory by default."""

_MB = 1024 * 1024


def run_command(args: Sequence[str]) -> str | None:
    """Run a probe command, returning stdout, or None if it is missing or fails."""
    try:
        completed = subprocess.run(  # fixed argv, never a shell
            list(args),
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_S,
            check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("Probe %s unavailable: %s", args[0], exc)
        return None
    return completed.stdout


def parse_nvidia_smi(output: str) -> list[GpuInfo]:
    gpus: list[GpuInfo] = []
    for line in output.splitlines():
        name, sep, memory = line.rpartition(",")
        if not sep:
            continue
        try:
            memory_mb = int(float(memory.strip()))
        except ValueError:
            logger.warning("Unparseable nvidia-smi line: %r", line)
            continue
        gpus.append(
            GpuInfo(name=name.strip(), backend="cuda", memory_mb=memory_mb, unified_memory=False)
        )
    return gpus


def _apple_silicon_gpu(total_ram_mb: int) -> GpuInfo:
    return GpuInfo(
        name="Apple Silicon GPU",
        backend="metal",
        memory_mb=int(total_ram_mb * APPLE_GPU_SHARE),
        unified_memory=True,
    )


def detect_hardware(
    *,
    run: CommandRunner = run_command,
    system: str | None = None,
    machine: str | None = None,
) -> HardwareProfile:
    system = system or platform.system()
    machine = machine or platform.machine()
    memory = psutil.virtual_memory()
    total_ram_mb = memory.total // _MB
    logical = psutil.cpu_count(logical=True) or 1
    physical = psutil.cpu_count(logical=False) or logical

    gpus: list[GpuInfo] = []
    if system == "Darwin" and machine == "arm64":
        gpus.append(_apple_silicon_gpu(total_ram_mb))
    else:
        output = run(NVIDIA_SMI_QUERY)
        if output:
            gpus.extend(parse_nvidia_smi(output))

    return HardwareProfile(
        os=system,
        arch=machine,
        cpu_physical_cores=physical,
        cpu_logical_cores=logical,
        total_ram_mb=total_ram_mb,
        available_ram_mb=memory.available // _MB,
        gpus=gpus,
    )

"""Engine process settings, resolved once at startup and then immutable."""

from dataclasses import dataclass, field

LOOPBACK_HOST = "127.0.0.1"
"""The engine only ever listens on loopback; it is never exposed to the network."""

MIN_TOKEN_LENGTH = 16

DEFAULT_ALLOWED_ORIGINS: tuple[str, ...] = (
    "http://localhost:1420",  # Vite dev server used by `tauri dev`
    "tauri://localhost",  # Tauri production webview (macOS/Linux)
    "http://tauri.localhost",  # Tauri production webview (Windows)
)


@dataclass(frozen=True, slots=True)
class EngineSettings:
    port: int
    token: str
    parent_pid: int | None = None
    allowed_origins: tuple[str, ...] = field(default=DEFAULT_ALLOWED_ORIGINS)

    def __post_init__(self) -> None:
        if not 0 < self.port < 65536:
            raise ValueError(f"port must be in 1..65535, got {self.port}")
        if len(self.token) < MIN_TOKEN_LENGTH:
            raise ValueError(f"token must be at least {MIN_TOKEN_LENGTH} characters")

import pytest

from rb_engine.__main__ import TOKEN_ENV_VAR, _parse_settings
from rb_engine.runtime.settings import EngineSettings


@pytest.mark.parametrize("port", [0, 65536, -1])
def test_rejects_invalid_port(port: int) -> None:
    with pytest.raises(ValueError, match="port"):
        EngineSettings(port=port, token="x" * 16)


def test_rejects_short_token() -> None:
    with pytest.raises(ValueError, match="token"):
        EngineSettings(port=8765, token="short")


def test_token_read_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TOKEN_ENV_VAR, "env-token-0123456789")
    settings = _parse_settings(["--port", "9000", "--parent-pid", "42"])
    assert settings.token == "env-token-0123456789"
    assert settings.parent_pid == 42


def test_missing_token_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(TOKEN_ENV_VAR, raising=False)
    with pytest.raises(SystemExit):
        _parse_settings(["--port", "9000"])

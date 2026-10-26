"""API keys live in the OS credential store (Windows Credential Manager, macOS Keychain,
Secret Service on Linux), never in plain-text preference files."""

import contextlib
import logging
from typing import Protocol

import keyring
import keyring.errors

logger = logging.getLogger(__name__)

SERVICE = "ResearchBrowser"


class SecretStore(Protocol):
    def available(self) -> bool: ...

    def get(self, name: str) -> str | None: ...

    def set(self, name: str, value: str) -> None: ...

    def delete(self, name: str) -> None: ...


class SecretStorageUnavailableError(Exception):
    pass


class KeyringSecretStore:
    def available(self) -> bool:
        try:
            backend = keyring.get_keyring()
        except keyring.errors.KeyringError:
            return False
        # The "fail" backend is what keyring uses when no secure store exists.
        return "fail" not in type(backend).__module__

    def get(self, name: str) -> str | None:
        if not self.available():
            return None
        try:
            return keyring.get_password(SERVICE, name)
        except keyring.errors.KeyringError:
            logger.warning("Could not read %s from the credential store", name)
            return None

    def set(self, name: str, value: str) -> None:
        if not self.available():
            raise SecretStorageUnavailableError("No secure credential store on this system")
        keyring.set_password(SERVICE, name, value)

    def delete(self, name: str) -> None:
        if not self.available():
            return
        with contextlib.suppress(keyring.errors.PasswordDeleteError):  # nothing stored
            keyring.delete_password(SERVICE, name)


class MemorySecretStore:
    """For tests and systems without a credential store."""

    def __init__(self, *, available: bool = True) -> None:
        self._available = available
        self.values: dict[str, str] = {}

    def available(self) -> bool:
        return self._available

    def get(self, name: str) -> str | None:
        return self.values.get(name)

    def set(self, name: str, value: str) -> None:
        if not self._available:
            raise SecretStorageUnavailableError("No secure credential store on this system")
        self.values[name] = value

    def delete(self, name: str) -> None:
        self.values.pop(name, None)

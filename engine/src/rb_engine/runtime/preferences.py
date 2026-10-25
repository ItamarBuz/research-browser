"""User preferences persisted as JSON in the data directory."""

import logging
import os
import tempfile
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from rb_engine.domain.hardware import Tier

logger = logging.getLogger(__name__)


class UserPreferences(BaseModel):
    # Unknown keys are ignored so files written by newer app versions still load.
    model_config = ConfigDict(extra="ignore", frozen=True)

    tier_override: Tier | None = None


class PreferencesStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> UserPreferences:
        try:
            raw = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return UserPreferences()
        try:
            return UserPreferences.model_validate_json(raw)
        except ValidationError:
            # A broken preferences file must never stop the app from starting.
            logger.warning("Ignoring unreadable preferences file %s", self._path)
            return UserPreferences()

    def save(self, preferences: UserPreferences) -> None:
        """Write atomically so a crash mid-write cannot leave a truncated file."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=self._path.parent, prefix=".preferences-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp:
                tmp.write(preferences.model_dump_json(indent=2))
            Path(tmp_name).replace(self._path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise

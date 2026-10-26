"""Where the engine keeps its data (models, indexes, preferences) on disk."""

import os
from dataclasses import dataclass
from pathlib import Path

import platformdirs

DATA_DIR_ENV_VAR = "RB_DATA_DIR"
APP_DIR_NAME = "ResearchBrowser"


@dataclass(frozen=True, slots=True)
class DataPaths:
    root: Path

    @property
    def models(self) -> Path:
        return self.root / "models"

    @property
    def preferences(self) -> Path:
        return self.root / "preferences.json"

    @property
    def library(self) -> Path:
        return self.root / "library"

    @property
    def library_db(self) -> Path:
        return self.library / "library.sqlite3"

    @property
    def library_files(self) -> Path:
        """Imported PDFs, stored as <sha256>.pdf so the original may move or be deleted."""
        return self.library / "files"

    @property
    def library_incoming(self) -> Path:
        """Uploads in progress; moved into library_files once complete."""
        return self.library / "incoming"

    @property
    def library_index(self) -> Path:
        return self.library / "index"

    @property
    def http_cache(self) -> Path:
        """Responses from online academic sources, for speed and offline use."""
        return self.root / "cache" / "http.sqlite3"

    def ensure(self) -> "DataPaths":
        for directory in (self.models, self.library_files, self.library_incoming):
            directory.mkdir(parents=True, exist_ok=True)
        return self


def resolve_data_dir(explicit: Path | None = None) -> Path:
    """`--data-dir`, then RB_DATA_DIR, then the OS's per-user application data folder."""
    if explicit is not None:
        return explicit
    from_env = os.environ.get(DATA_DIR_ENV_VAR)
    if from_env:
        return Path(from_env)
    return Path(platformdirs.user_data_dir(APP_DIR_NAME, appauthor=False))

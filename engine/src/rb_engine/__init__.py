"""Research Browser engine: local-first academic search, scoring and analysis."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("rb-engine")
except PackageNotFoundError:  # running from a source tree without an installed dist
    __version__ = "0.0.0+unknown"

API_VERSION = 1
"""Bumped on breaking changes to the HTTP contract the desktop app depends on."""

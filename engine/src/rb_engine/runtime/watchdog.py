"""Stops the engine when the desktop shell that launched it goes away.

Killing a sidecar from the parent is not reliable on every OS (e.g. `uv run` wrappers on
Windows leave the Python grandchild behind), so the engine also watches its parent itself.
"""

import logging
import threading
from collections.abc import Callable

import psutil

logger = logging.getLogger(__name__)


def watch_parent(
    parent_pid: int, on_parent_exit: Callable[[], None], interval_s: float = 2.0
) -> threading.Thread:
    """Start a daemon thread that calls `on_parent_exit` once `parent_pid` stops running."""

    def _run() -> None:
        while psutil.pid_exists(parent_pid):
            threading.Event().wait(interval_s)
        logger.info("Parent process %d exited; shutting down engine", parent_pid)
        on_parent_exit()

    thread = threading.Thread(target=_run, name="parent-watchdog", daemon=True)
    thread.start()
    return thread

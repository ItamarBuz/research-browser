"""Limits how many heavy models are loaded in memory at once.

Callers lease a model for the duration of a pipeline stage. When the resident limit is
reached, the least recently used idle model is unloaded; if every resident model is in use,
the caller waits. On Lite the limit is 1, which turns the pipeline into a sequence of
stages that each have the machine's memory to themselves.
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from itertools import count
from typing import cast

from rb_engine.domain.hardware import Tier

logger = logging.getLogger(__name__)

RESIDENT_LIMITS: dict[Tier, int] = {Tier.LITE: 1, Tier.STANDARD: 2, Tier.PRO: 4}
"""Unloading calls the resource's `close()` method when it has one."""


@dataclass
class _Entry:
    resource: object
    leases: int
    last_used: int


class ResidencyManager:
    def __init__(self, max_resident: int) -> None:
        if max_resident < 1:
            raise ValueError("max_resident must be at least 1")
        self._max = max_resident
        self._entries: dict[str, _Entry] = {}
        self._loading: set[str] = set()
        self._changed = asyncio.Condition()
        self._clock = count()

    @property
    def resident(self) -> list[str]:
        return list(self._entries)

    async def set_limit(self, max_resident: int) -> None:
        """Change the limit (e.g. after a tier change); idle models above it are unloaded."""
        if max_resident < 1:
            raise ValueError("max_resident must be at least 1")
        async with self._changed:
            self._max = max_resident
            while len(self._entries) > self._max and self._evict_one():
                pass
            self._changed.notify_all()

    @asynccontextmanager
    async def lease[T](self, key: str, loader: Callable[[], T]) -> AsyncIterator[T]:
        """Yield the loaded resource for `key`, loading it (in a thread) if needed."""
        resource = await self._acquire(key, loader)
        try:
            yield resource
        finally:
            async with self._changed:
                entry = self._entries[key]
                entry.leases -= 1
                entry.last_used = next(self._clock)
                self._changed.notify_all()

    async def _acquire[T](self, key: str, loader: Callable[[], T]) -> T:
        async with self._changed:
            while True:
                if key in self._entries:
                    entry = self._entries[key]
                    entry.leases += 1
                    return cast("T", entry.resource)
                if key not in self._loading and self._make_room():
                    self._loading.add(key)
                    break
                await self._changed.wait()

        try:
            resource = await asyncio.to_thread(loader)
        except BaseException:
            async with self._changed:
                self._loading.discard(key)
                self._changed.notify_all()
            raise

        async with self._changed:
            self._loading.discard(key)
            self._entries[key] = _Entry(resource=resource, leases=1, last_used=next(self._clock))
            self._changed.notify_all()
        logger.info("Loaded %s (%d/%d resident)", key, len(self._entries), self._max)
        return resource

    def _make_room(self) -> bool:
        """Free a slot for one more model if possible. Caller holds the condition lock."""
        while len(self._entries) + len(self._loading) >= self._max:
            if not self._evict_one():
                return False
        return True

    def _evict_one(self) -> bool:
        idle = [(e.last_used, k) for k, e in self._entries.items() if e.leases == 0]
        if not idle:
            return False
        _, key = min(idle)
        entry = self._entries.pop(key)
        close = getattr(entry.resource, "close", None)
        if callable(close):
            close()
        logger.info("Unloaded %s", key)
        return True

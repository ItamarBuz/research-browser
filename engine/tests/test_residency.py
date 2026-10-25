import asyncio

import pytest

from rb_engine.runtime.residency import ResidencyManager

pytestmark = pytest.mark.anyio


class FakeModel:
    def __init__(self, name: str, log: list[str]) -> None:
        self.name = name
        self._log = log
        log.append(f"load {name}")

    def close(self) -> None:
        self._log.append(f"close {self.name}")


async def test_reuses_a_loaded_model() -> None:
    log: list[str] = []
    residency = ResidencyManager(2)

    async with residency.lease("a", lambda: FakeModel("a", log)) as first:
        pass
    async with residency.lease("a", lambda: FakeModel("a", log)) as second:
        assert second is first

    assert log == ["load a"]


async def test_evicts_least_recently_used_idle_model() -> None:
    log: list[str] = []
    residency = ResidencyManager(2)

    for name in ["a", "b", "a", "c"]:
        async with residency.lease(name, lambda n=name: FakeModel(n, log)):
            pass

    assert log == ["load a", "load b", "close b", "load c"]
    assert sorted(residency.resident) == ["a", "c"]


async def test_waits_while_all_slots_are_leased() -> None:
    log: list[str] = []
    residency = ResidencyManager(1)
    release_a = asyncio.Event()

    async def hold_a() -> None:
        async with residency.lease("a", lambda: FakeModel("a", log)):
            await release_a.wait()

    holder = asyncio.create_task(hold_a())
    await asyncio.sleep(0.05)

    async def use_b() -> None:
        async with residency.lease("b", lambda: FakeModel("b", log)):
            pass

    waiter = asyncio.create_task(use_b())
    await asyncio.sleep(0.05)
    assert log == ["load a"]  # b is blocked behind a

    release_a.set()
    await asyncio.wait_for(asyncio.gather(holder, waiter), timeout=2)
    assert log == ["load a", "close a", "load b"]


async def test_lowering_the_limit_unloads_idle_models() -> None:
    log: list[str] = []
    residency = ResidencyManager(3)
    for name in ["a", "b", "c"]:
        async with residency.lease(name, lambda n=name: FakeModel(n, log)):
            pass

    await residency.set_limit(1)

    assert residency.resident == ["c"]


async def test_failed_load_frees_the_slot() -> None:
    log: list[str] = []
    residency = ResidencyManager(1)

    def broken() -> FakeModel:
        raise RuntimeError("bad weights")

    with pytest.raises(RuntimeError):
        async with residency.lease("a", broken):
            pass
    async with residency.lease("b", lambda: FakeModel("b", log)):
        pass

    assert log == ["load b"]

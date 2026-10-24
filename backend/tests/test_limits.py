import asyncio

import pytest

from backend.app.core.limits import AsyncConcurrencyGate, QueueTimeoutError


def test_memory_daily_quota_denies_requests_over_limit():
    from backend.app.core.limits import MemoryDailyQuota

    quota = MemoryDailyQuota()

    assert quota.consume("user-1", limit=2) is True
    assert quota.consume("user-1", limit=2) is True
    assert quota.consume("user-1", limit=2) is False
    assert quota.consume("user-2", limit=2) is True


def test_concurrency_gate_times_out_waiting_request():
    async def scenario():
        gate = AsyncConcurrencyGate(limit=1, timeout_seconds=0.01)
        entered = asyncio.Event()
        release = asyncio.Event()

        async def hold_slot():
            async with gate.slot():
                entered.set()
                await release.wait()

        holder = asyncio.create_task(hold_slot())
        await entered.wait()
        with pytest.raises(QueueTimeoutError):
            async with gate.slot():
                pass
        release.set()
        await holder

    asyncio.run(scenario())

"""Tests for the process registry system."""

import asyncio

import pytest

from hive.ps import Process, ProcessContext, ProcessRegistry, ProcessState, ProcessStoppedError


class CountProcess(Process):
    """Finite process that counts to N."""

    name = "counter"
    description = "Counts to N"

    def __init__(self, n: int = 5):
        self.n = n
        self.count = 0

    async def run(self, ctx: ProcessContext) -> str:
        for i in range(self.n):
            await ctx.check()
            self.count += 1
            await asyncio.sleep(0)
        return f"counted to {self.n}"


class FailProcess(Process):
    """Process that raises an exception."""

    name = "failer"
    description = "Always fails"

    async def run(self, ctx: ProcessContext) -> str:
        raise RuntimeError("intentional failure")


class LongProcess(Process):
    """Long-running process that loops until stopped."""

    name = "long"
    description = "Runs until stopped"

    def __init__(self):
        self.iterations = 0

    async def run(self, ctx: ProcessContext) -> str:
        while True:
            await ctx.check()
            self.iterations += 1
            await asyncio.sleep(0.01)


class TestProcessContext:
    async def test_check_passes_normally(self):
        ctx = ProcessContext()
        await ctx.check()  # Should not raise

    async def test_check_raises_on_stop(self):
        ctx = ProcessContext()
        ctx.stop_event.set()
        with pytest.raises(ProcessStoppedError):
            await ctx.check()

    async def test_pause_blocks(self):
        ctx = ProcessContext()
        ctx.pause()
        assert ctx.paused

        # Set stop after a short delay to unblock
        async def _stop():
            await asyncio.sleep(0.05)
            ctx.stop_event.set()

        asyncio.create_task(_stop())
        with pytest.raises(ProcessStoppedError):
            await ctx.check()

    async def test_resume_unblocks(self):
        ctx = ProcessContext()
        ctx.pause()
        assert ctx.paused
        ctx.resume()
        assert not ctx.paused
        await ctx.check()  # Should not block


class TestProcessRegistry:
    async def test_register_and_status(self):
        ps = ProcessRegistry()
        ps.register(CountProcess())
        status = ps.status()
        assert len(status) == 1
        assert status[0]["name"] == "counter"
        assert status[0]["state"] == "pending"

    async def test_start_finite_process(self):
        ps = ProcessRegistry()
        proc = CountProcess(n=3)
        ps.register(proc)
        await ps.start("counter")
        # Wait for completion
        await asyncio.sleep(0.1)
        assert proc.count == 3
        assert ps.get_state("counter") == ProcessState.completed
        status = ps.status()
        assert status[0]["result"] == "counted to 3"

    async def test_start_unknown_raises(self):
        ps = ProcessRegistry()
        with pytest.raises(KeyError):
            await ps.start("nonexistent")

    async def test_stop_long_process(self):
        ps = ProcessRegistry()
        proc = LongProcess()
        ps.register(proc)
        await ps.start("long")
        await asyncio.sleep(0.05)
        assert proc.iterations > 0
        await ps.stop("long")
        assert ps.get_state("long") == ProcessState.stopped

    async def test_error_state(self):
        ps = ProcessRegistry()
        ps.register(FailProcess())
        await ps.start("failer")
        await asyncio.sleep(0.1)
        assert ps.get_state("failer") == ProcessState.error
        status = ps.status()
        assert status[0]["error"] == "intentional failure"

    async def test_pause_resume(self):
        ps = ProcessRegistry()
        proc = LongProcess()
        ps.register(proc)
        await ps.start("long")
        await asyncio.sleep(0.05)

        ps.pause("long")
        assert ps.get_state("long") == ProcessState.paused
        count_at_pause = proc.iterations
        await asyncio.sleep(0.05)
        # Should not have progressed much (cooperative pause)
        assert proc.iterations <= count_at_pause + 1

        ps.resume("long")
        assert ps.get_state("long") == ProcessState.running
        await asyncio.sleep(0.15)
        assert proc.iterations > count_at_pause

        await ps.stop("long")

    async def test_restart(self):
        ps = ProcessRegistry()
        proc = CountProcess(n=3)
        ps.register(proc)
        await ps.start("counter")
        await asyncio.sleep(0.1)
        assert proc.count == 3
        # Restart resets the task
        proc.count = 0
        await ps.restart("counter")
        await asyncio.sleep(0.1)
        assert proc.count == 3

    async def test_stop_all(self):
        ps = ProcessRegistry()
        ps.register(LongProcess())
        ps.register(CountProcess(n=1000))
        await ps.start("long")
        await ps.start("counter")
        await asyncio.sleep(0.05)
        await ps.stop_all()
        for s in ps.status():
            assert s["state"] in ("stopped", "completed")

    async def test_multiple_processes(self):
        ps = ProcessRegistry()
        ps.register(CountProcess(n=5))
        ps.register(FailProcess())
        await ps.start("counter")
        await ps.start("failer")
        await asyncio.sleep(0.1)
        assert ps.get_state("counter") == ProcessState.completed
        assert ps.get_state("failer") == ProcessState.error

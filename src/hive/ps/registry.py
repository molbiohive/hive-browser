"""ProcessRegistry — centralized lifecycle management for background tasks."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime

from hive.ps.base import Process, ProcessContext, ProcessInfo, ProcessState, ProcessStoppedError

logger = logging.getLogger(__name__)


class ProcessRegistry:
    """Manages registration, lifecycle, and status of background processes."""

    def __init__(self):
        self._processes: dict[str, Process] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._contexts: dict[str, ProcessContext] = {}
        self._info: dict[str, ProcessInfo] = {}

    def register(self, process: Process) -> None:
        """Register a process. Does not start it."""
        self._processes[process.name] = process
        self._info[process.name] = ProcessInfo(
            name=process.name,
            description=process.description,
        )

    async def start(self, name: str) -> None:
        """Start a registered process as an asyncio task."""
        if name not in self._processes:
            raise KeyError(f"Unknown process: {name}")

        # Stop existing task if running
        if name in self._tasks and not self._tasks[name].done():
            await self.stop(name)

        ctx = ProcessContext()
        self._contexts[name] = ctx
        info = self._info[name]
        info.state = ProcessState.running
        info.started_at = datetime.now(UTC)
        info.finished_at = None
        info.error = None
        info.result = None

        self._tasks[name] = asyncio.create_task(
            self._run_wrapper(name, ctx),
            name=f"ps:{name}",
        )

    async def _run_wrapper(self, name: str, ctx: ProcessContext) -> None:
        """Wrapper that catches exceptions and updates ProcessInfo."""
        info = self._info[name]
        try:
            result = await self._processes[name].run(ctx)
            info.state = ProcessState.completed
            info.result = result
        except ProcessStoppedError:
            info.state = ProcessState.stopped
        except asyncio.CancelledError:
            info.state = ProcessState.stopped
        except Exception as e:
            info.state = ProcessState.error
            info.error = str(e)
            logger.error("Process %s failed: %s", name, e)
        finally:
            info.finished_at = datetime.now(UTC)

    async def stop(self, name: str) -> None:
        """Stop a running process."""
        if name not in self._processes:
            raise KeyError(f"Unknown process: {name}")

        ctx = self._contexts.get(name)
        if ctx:
            ctx.stop_event.set()

        task = self._tasks.get(name)
        if task and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        info = self._info.get(name)
        if info and info.state in (ProcessState.running, ProcessState.paused):
            info.state = ProcessState.stopped
            info.finished_at = datetime.now(UTC)

    def pause(self, name: str) -> None:
        """Pause a running process (cooperative — waits for next ctx.check())."""
        if name not in self._processes:
            raise KeyError(f"Unknown process: {name}")

        ctx = self._contexts.get(name)
        if ctx:
            ctx.pause()
        info = self._info.get(name)
        if info and info.state == ProcessState.running:
            info.state = ProcessState.paused

    def resume(self, name: str) -> None:
        """Resume a paused process."""
        if name not in self._processes:
            raise KeyError(f"Unknown process: {name}")

        ctx = self._contexts.get(name)
        if ctx:
            ctx.resume()
        info = self._info.get(name)
        if info and info.state == ProcessState.paused:
            info.state = ProcessState.running

    async def restart(self, name: str) -> None:
        """Stop and start a process."""
        await self.stop(name)
        await self.start(name)

    def status(self) -> list[dict]:
        """Return status of all registered processes."""
        return [info.to_dict() for info in self._info.values()]

    def get_state(self, name: str) -> ProcessState | None:
        """Get current state of a process."""
        info = self._info.get(name)
        return info.state if info else None

    async def stop_all(self) -> None:
        """Stop all running processes (for shutdown)."""
        for name in list(self._processes):
            task = self._tasks.get(name)
            if task and not task.done():
                await self.stop(name)

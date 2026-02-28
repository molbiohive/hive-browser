"""Process primitives — state, context, and abstract base class."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ProcessState(StrEnum):
    pending = "pending"
    running = "running"
    paused = "paused"
    stopped = "stopped"
    completed = "completed"
    error = "error"


class ProcessStoppedError(Exception):
    """Raised by ProcessContext.check() when stop is requested."""


class ProcessContext:
    """Cooperative control for a running process.

    Processes call ``await ctx.check()`` at safe points to:
    - Block while paused
    - Raise ProcessStoppedError if stop was requested
    """

    def __init__(self):
        self.stop_event = asyncio.Event()
        self._pause_event = asyncio.Event()  # set = paused

    async def check(self):
        """Check for stop/pause signals. Call between work units."""
        if self.stop_event.is_set():
            raise ProcessStoppedError()
        while self._pause_event.is_set():
            if self.stop_event.is_set():
                raise ProcessStoppedError()
            await asyncio.sleep(0.1)

    def pause(self):
        self._pause_event.set()

    def resume(self):
        self._pause_event.clear()

    @property
    def paused(self) -> bool:
        return self._pause_event.is_set()


@dataclass
class ProcessInfo:
    """Snapshot of a process's state for reporting."""

    name: str
    description: str
    state: ProcessState = ProcessState.pending
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    result: str | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "state": self.state.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "error": self.error,
            "result": self.result,
        }


class Process(ABC):
    """Base class for a managed background process."""

    name: str
    description: str

    @abstractmethod
    async def run(self, ctx: ProcessContext) -> str | None:
        """Execute the process. Return optional result string."""
        ...

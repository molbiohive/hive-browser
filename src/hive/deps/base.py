"""Dep ABC and DepRegistry — unified interface for external binary dependencies."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class Dep(ABC):
    """Base class for external binary dependencies (BLAST+, MAFFT, etc.).

    Each dep provides binary resolution, health checks, subprocess execution,
    and optional index rebuilding after file ingest.
    """

    name: str
    needs_rebuild_on_ingest: bool = False

    @abstractmethod
    def resolve_binary(self, program: str) -> str:
        """Return full path to a binary, or just the program name if using PATH."""
        ...

    async def health(self) -> dict[str, Any]:
        """Check if the dependency is available. Returns {"ok": bool, "version": str|None}."""
        return {"ok": False, "version": None}

    async def setup(self) -> bool:
        """One-time setup on startup (e.g. build index). No-op by default."""
        return True

    async def rebuild(self) -> bool:
        """Rebuild after ingest. Delegates to setup() by default."""
        return await self.setup()

    @staticmethod
    async def _run(cmd: list[str]) -> tuple[int, bytes, bytes]:
        """Shared subprocess helper. Returns (returncode, stdout, stderr)."""
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return proc.returncode, stdout, stderr


class DepRegistry:
    """Central registry of external dependencies."""

    def __init__(self):
        self._deps: dict[str, Dep] = {}

    def register(self, dep: Dep):
        self._deps[dep.name] = dep

    def get(self, name: str) -> Dep | None:
        return self._deps.get(name)

    def all(self) -> list[Dep]:
        return list(self._deps.values())

    def rebuild_targets(self) -> list[Dep]:
        """Deps that need rebuilding after file ingest."""
        return [d for d in self._deps.values() if d.needs_rebuild_on_ingest]

    async def setup_all(self) -> dict[str, bool]:
        """Run setup() on all deps. Returns {name: success}."""
        results = {}
        for dep in self._deps.values():
            try:
                results[dep.name] = await dep.setup()
            except Exception as e:
                logger.warning("Dep %s setup failed: %s", dep.name, e)
                results[dep.name] = False
        return results

    async def rebuild_all(self) -> dict[str, bool]:
        """Rebuild all deps that need it after ingest."""
        results = {}
        for dep in self.rebuild_targets():
            try:
                results[dep.name] = await dep.rebuild()
            except Exception as e:
                logger.warning("Dep %s rebuild failed: %s", dep.name, e)
                results[dep.name] = False
        return results

    async def health_all(self) -> dict[str, dict]:
        """Health check all deps. Returns {name: {"ok": bool, "version": ...}}."""
        results = {}
        for dep in self._deps.values():
            try:
                results[dep.name] = await dep.health()
            except Exception as e:
                logger.warning("Dep %s health check failed: %s", dep.name, e)
                results[dep.name] = {"ok": False, "version": None}
        return results

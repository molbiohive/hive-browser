"""MAFFT dependency — multiple sequence alignment."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from hive.deps import Dep

logger = logging.getLogger(__name__)


class MafftDep(Dep):
    """MAFFT external dependency — multiple sequence alignment."""

    name = "mafft"
    needs_rebuild_on_ingest = False

    def __init__(self, bin_dir: str = ""):
        self._bin_dir = bin_dir

    def resolve_binary(self, program: str) -> str:
        if self._bin_dir:
            return str(Path(self._bin_dir) / program)
        return program

    async def health(self) -> dict[str, Any]:
        binary = self.resolve_binary("mafft")
        try:
            rc, _, stderr = await self._run([binary, "--version"])
            # mafft --version prints to stderr and exits 0 (or 1 on some versions)
            version = stderr.decode().strip().split("\n")[0] if stderr else None
            if rc in (0, 1) and version:
                return {"ok": True, "version": version}
        except FileNotFoundError:
            pass
        return {"ok": False, "version": None}

    async def align(
        self,
        sequences: list[tuple[str, str]],
        algorithm: str = "auto",
    ) -> dict[str, Any]:
        """Align sequences using MAFFT.

        Args:
            sequences: List of (name, sequence) tuples.
            algorithm: "auto", "linsi", "ginsi", "einsi", or "fftns".

        Returns:
            {"aligned": str, "count": int, "error": str|None}
        """
        if len(sequences) < 2:
            return {"error": "Need at least 2 sequences to align", "aligned": "", "count": 0}

        # Write input FASTA
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".fasta", delete=False,
        ) as f:
            for name, seq in sequences:
                safe = name.replace(" ", "_")
                f.write(f">{safe}\n{seq}\n")
            input_file = f.name

        binary = self.resolve_binary("mafft")
        cmd = [binary]

        if algorithm == "auto":
            cmd.append("--auto")
        elif algorithm in ("linsi", "ginsi", "einsi", "fftns"):
            cmd.append(f"--{algorithm}")
        else:
            cmd.append("--auto")

        cmd.append(input_file)

        try:
            # MAFFT's shell wrapper opens /dev/stderr by path, which may
            # not exist in Docker containers.  Create the symlink if missing.
            if not os.path.exists("/dev/stderr"):
                try:
                    os.symlink("/proc/self/fd/2", "/dev/stderr")
                except OSError:
                    pass
            rc, stdout, stderr = await self._run(cmd)
        finally:
            Path(input_file).unlink(missing_ok=True)

        if rc != 0:
            err = stderr.decode().strip()
            logger.error("MAFFT failed: %s", err)
            return {"error": f"MAFFT error: {err}", "aligned": "", "count": 0}

        aligned = stdout.decode()
        return {
            "aligned": aligned,
            "count": len(sequences),
        }

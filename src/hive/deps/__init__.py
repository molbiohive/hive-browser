"""External binary dependencies — BLAST+, MAFFT, and registry."""

from hive.deps.base import Dep, DepRegistry
from hive.deps.blast import BlastDep
from hive.deps.mafft import MafftDep

__all__ = ["Dep", "DepRegistry", "BlastDep", "MafftDep"]

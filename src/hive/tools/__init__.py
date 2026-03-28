"""Tools package -- self-describing tool interface, registry, and factory."""

from hive.tools.base import Tool, ToolRegistry
from hive.tools.factory import ToolFactory

__all__ = ["Tool", "ToolRegistry", "ToolFactory"]

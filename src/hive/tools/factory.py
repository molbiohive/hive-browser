"""ToolFactory — discovers and registers internal tools."""

from __future__ import annotations

import importlib
import logging
import pkgutil
from inspect import isabstract
from typing import TYPE_CHECKING

from hive.tools.base import Tool, ToolRegistry

if TYPE_CHECKING:
    from hive.config import Settings

logger = logging.getLogger(__name__)


class ToolFactory:
    """Discover and instantiate tools from internal modules."""

    @staticmethod
    def discover(config: Settings) -> ToolRegistry:
        registry = ToolRegistry()
        _load_internal(registry, config)
        return registry


def _load_internal(registry: ToolRegistry, config: Settings):
    """Scan hive.tools.* for Tool subclasses and register them."""
    import hive.tools as tools_pkg

    skip = {"base", "factory", "resolve"}
    kwargs = {"config": config}

    for info in pkgutil.iter_modules(tools_pkg.__path__):
        if info.name in skip:
            continue
        try:
            mod = importlib.import_module(f"hive.tools.{info.name}")
        except Exception as e:
            logger.warning("Failed to import hive.tools.%s: %s", info.name, e)
            continue

        for attr_name in dir(mod):
            cls = getattr(mod, attr_name)
            if (
                isinstance(cls, type)
                and issubclass(cls, Tool)
                and cls is not Tool
                and not isabstract(cls)
                and hasattr(cls, "name")
            ):
                try:
                    tool = cls(**kwargs)
                    registry.register(tool)
                    logger.debug("Registered internal tool: %s", tool.name)
                except Exception as e:
                    logger.warning("Failed to instantiate %s: %s", attr_name, e)

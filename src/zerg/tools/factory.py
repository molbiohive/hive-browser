"""ToolFactory — discovers and registers internal + external tools."""

from __future__ import annotations

import ast
import importlib
import importlib.util
import logging
import pkgutil
from inspect import isabstract
from pathlib import Path
from typing import TYPE_CHECKING

from zerg.tools.base import Tool, ToolRegistry

if TYPE_CHECKING:
    from zerg.config import Settings
    from zerg.llm.client import LLMClient

logger = logging.getLogger(__name__)

# Internal modules that external tools must NOT import
_FORBIDDEN_PREFIXES = ("zerg.db", "zerg.server", "zerg.tools", "zerg.llm", "zerg.config")
# Allowed internal imports
_ALLOWED_PREFIXES = ("zerg.sdk",)


class ToolFactory:
    """Discover and instantiate tools from internal modules and external scripts."""

    @staticmethod
    def discover(config: Settings, llm_client: LLMClient | None = None) -> ToolRegistry:
        registry = ToolRegistry()
        _load_internal(registry, config, llm_client)
        _load_external(registry, config)
        return registry


def _load_internal(registry: ToolRegistry, config: Settings, llm_client: LLMClient | None):
    """Scan zerg.tools.* for Tool subclasses and register them."""
    import zerg.tools as tools_pkg

    skip = {"base", "router", "factory"}
    kwargs = {"config": config, "llm_client": llm_client}

    for info in pkgutil.iter_modules(tools_pkg.__path__):
        if info.name in skip:
            continue
        try:
            mod = importlib.import_module(f"zerg.tools.{info.name}")
        except Exception as e:
            logger.warning("Failed to import zerg.tools.%s: %s", info.name, e)
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


def _load_external(registry: ToolRegistry, config: Settings):
    """Load external tool scripts from the tools directory."""
    tools_dir = Path(config.tools.directory).expanduser()
    if not tools_dir.is_dir():
        logger.debug("External tools directory not found: %s", tools_dir)
        return

    for py_file in sorted(tools_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue

        source = py_file.read_text()

        # Validate imports before loading
        violations = _validate_imports(source)
        if violations:
            for v in violations:
                logger.warning(
                    "Skipping %s: forbidden import '%s' — use zerg.sdk instead",
                    py_file.name, v,
                )
            continue

        try:
            tool = _load_tool_from_file(py_file, source)
        except Exception as e:
            logger.warning("Failed to load external tool %s: %s", py_file.name, e)
            continue

        if tool is None:
            logger.warning("No Tool subclass found in %s", py_file.name)
            continue

        if not tool.name or not tool.description:
            logger.warning("Skipping %s: missing name or description", py_file.name)
            continue

        if existing := registry.get(tool.name):
            logger.warning(
                "External tool '%s' overrides internal tool from %s",
                tool.name, type(existing).__module__,
            )

        registry.register(tool)
        logger.info("Registered external tool: %s (%s)", tool.name, py_file.name)


def _load_tool_from_file(py_file: Path, source: str) -> Tool | None:
    """Import a .py file and find the first Tool subclass, inject ToolDB."""
    module_name = f"zerg_ext_tools.{py_file.stem}"
    spec = importlib.util.spec_from_file_location(module_name, py_file)
    if spec is None or spec.loader is None:
        return None

    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Find the first concrete Tool subclass
    tool_cls = None
    for attr_name in dir(mod):
        cls = getattr(mod, attr_name)
        if (
            isinstance(cls, type)
            and issubclass(cls, Tool)
            and cls is not Tool
            and not isabstract(cls)
            and hasattr(cls, "name")
        ):
            tool_cls = cls
            break

    if tool_cls is None:
        return None

    tool = tool_cls()

    # Inject read-only DB access
    from zerg.sdk.db import ToolDB
    tool.db = ToolDB()

    return tool


def _validate_imports(source: str) -> list[str]:
    """Check that source only imports from allowed modules.

    Returns list of forbidden import strings, empty if valid.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ["<syntax error>"]

    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_forbidden(alias.name):
                    violations.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module and _is_forbidden(node.module):
            violations.append(node.module)

    return violations


def _is_forbidden(module: str) -> bool:
    """Check if a module import is forbidden for external tools."""
    # Allow zerg.sdk and submodules
    if any(module == p or module.startswith(p + ".") for p in _ALLOWED_PREFIXES):
        return False
    # Forbid other zerg internals
    return any(
        module == p or module.startswith(p + ".")
        for p in _FORBIDDEN_PREFIXES
    )

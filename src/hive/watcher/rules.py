"""Rule engine for file watcher — matches files against YAML-configured rules."""

import fnmatch
import logging
from dataclasses import dataclass
from pathlib import Path

from hive.config import WatcherRule

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    action: str  # 'parse' | 'ignore' | 'log'
    parser: str | None = None
    extract: list[str] | None = None
    message: str | None = None


def match_file(file_path: Path, rules: list[WatcherRule]) -> MatchResult:
    """Match a file against rules (top-down, first match wins)."""
    filename = file_path.name

    for rule in rules:
        if fnmatch.fnmatch(filename, rule.match):
            return MatchResult(
                action=rule.action,
                parser=rule.parser,
                extract=rule.extract or None,
                message=rule.message,
            )

    return MatchResult(action="log", message=f"No rule matched: {filename}")

"""Skill library -- serves skill procedures for the planner.

Primary mode: load from DB rows (list of dicts with name/content).
Fallback: load from disk directory (for tests or standalone use).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Skill:
    """A single skill procedure."""

    name: str
    when: str
    content: str


def _extract_when(content: str) -> str:
    """Extract text between ## When and the next ## heading."""
    m = re.search(r"## When\s*\n(.*?)(?=\n## |\Z)", content, re.DOTALL)
    return m.group(1).strip() if m else ""


class SkillLibrary:
    """Serve skill procedures from DB data or a disk directory."""

    def __init__(
        self,
        skills_dir: str | Path | None = None,
        *,
        skills_data: list[dict] | None = None,
    ):
        self._skills: dict[str, Skill] = {}
        if skills_data is not None:
            self._load_from_data(skills_data)
        elif skills_dir is not None:
            self._load_from_disk(Path(skills_dir))

    def _load_from_data(self, rows: list[dict]) -> None:
        """Load from DB rows: [{"name": ..., "content": ...}, ...]."""
        for row in rows:
            name = row["name"]
            content = row["content"]
            self._skills[name] = Skill(
                name=name, when=_extract_when(content), content=content,
            )

    def _load_from_disk(self, path: Path) -> None:
        """Load from a directory of .md files (tests/fallback)."""
        if not path.is_dir():
            return
        for fp in sorted(path.glob("*.md")):
            content = fp.read_text()
            name = fp.stem
            self._skills[name] = Skill(
                name=name, when=_extract_when(content), content=content,
            )

    def reload(self, skills_data: list[dict]) -> None:
        """Replace all skills from fresh DB data."""
        self._skills.clear()
        self._load_from_data(skills_data)

    def catalog(self) -> list[dict]:
        """Return name + when for all skills."""
        return [{"name": s.name, "when": s.when} for s in self._skills.values()]

    def read(self, name: str) -> str | None:
        """Return full content of a skill by name, or None."""
        skill = self._skills.get(name)
        return skill.content if skill else None

    def names(self) -> list[str]:
        """Return all skill names."""
        return list(self._skills.keys())

    def __len__(self) -> int:
        return len(self._skills)

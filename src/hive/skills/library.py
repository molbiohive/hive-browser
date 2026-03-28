"""Skill library -- loads .md skill procedures for the planner."""

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
    """Load and serve .md skill files from a directory."""

    def __init__(self, skills_dir: str | Path | None = None):
        if skills_dir is None:
            skills_dir = Path(__file__).parent
        self._dir = Path(skills_dir)
        self._skills: dict[str, Skill] = {}
        self._load()

    def _load(self) -> None:
        if not self._dir.is_dir():
            return
        for path in sorted(self._dir.glob("*.md")):
            content = path.read_text()
            name = path.stem
            when = _extract_when(content)
            self._skills[name] = Skill(name=name, when=when, content=content)

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

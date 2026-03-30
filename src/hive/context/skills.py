"""Skill service -- CRUD and bootstrap for planner skill procedures."""

from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hive.db import Skill

_REQUIRED_SECTIONS = ("When", "Tools", "Workflow", "Report", "Rules")


def validate_skill_content(content: str) -> list[str]:
    """Validate skill markdown structure. Returns list of errors (empty = valid)."""
    errors: list[str] = []
    if not re.match(r"^# .+", content):
        errors.append("Must start with # Title")
    headings = {h.strip() for h in re.findall(r"^## (.+)$", content, re.MULTILINE)}
    for section in _REQUIRED_SECTIONS:
        if section not in headings:
            errors.append(f"Missing required section: ## {section}")
    return errors


async def list_skills(session: AsyncSession) -> list[Skill]:
    """List all skills ordered by default first, then name."""
    stmt = select(Skill).order_by(Skill.is_default.desc(), Skill.name)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_skill(session: AsyncSession, skill_id: int) -> Skill | None:
    return (
        await session.execute(select(Skill).where(Skill.id == skill_id))
    ).scalar_one_or_none()


async def create_skill(
    session: AsyncSession, name: str, content: str,
) -> Skill:
    """Create a user skill (is_default=False)."""
    skill = Skill(name=name, content=content, is_default=False)
    session.add(skill)
    await session.flush()
    return skill


async def update_skill(
    session: AsyncSession,
    skill_id: int,
    name: str | None = None,
    content: str | None = None,
) -> Skill:
    skill = await get_skill(session, skill_id)
    if not skill:
        raise ValueError(f"Skill {skill_id} not found")
    if name is not None:
        skill.name = name
    if content is not None:
        skill.content = content
    await session.flush()
    return skill


async def delete_skill(session: AsyncSession, skill_id: int) -> bool:
    """Delete a skill. Rejects deletion of default (built-in) skills."""
    skill = await get_skill(session, skill_id)
    if not skill:
        return False
    if skill.is_default:
        raise ValueError("Cannot delete built-in skill")
    await session.delete(skill)
    await session.flush()
    return True


async def bootstrap_skills(session: AsyncSession) -> int:
    """Seed default skills from extras/skills/*.md. Idempotent."""
    skills_dir = Path(__file__).resolve().parents[3] / "extras" / "skills"
    if not skills_dir.is_dir():
        return 0

    # Load existing default skill names
    existing = set(
        (await session.execute(
            select(Skill.name).where(Skill.is_default.is_(True))
        )).scalars().all()
    )

    count = 0
    for path in sorted(skills_dir.glob("*.md")):
        name = path.stem
        if name in existing:
            continue
        content = path.read_text()
        session.add(Skill(name=name, content=content, is_default=True))
        count += 1

    if count:
        await session.flush()
    return count

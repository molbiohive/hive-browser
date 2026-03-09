"""Variant detection -- flag parts that share a name but have different sequences."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hive.db.models import PartName
from hive.libs import add_annotation

logger = logging.getLogger(__name__)


async def detect_name_collision(
    session: AsyncSession, part_id: int, name: str,
) -> list[int]:
    """Find other part IDs that share the same name but different part_id."""
    rows = (await session.execute(
        select(PartName.part_id).where(
            PartName.name == name,
            PartName.part_id != part_id,
        ).distinct()
    )).scalars().all()
    return list(rows)


async def flag_variant(
    session: AsyncSession, part_id: int, colliding_pids: list[int],
):
    """Write variant_of annotation linking to colliding part IDs."""
    if not colliding_pids:
        return
    value = ",".join(str(pid) for pid in sorted(colliding_pids))
    await add_annotation(session, part_id, "variant_of", value, source="computed")

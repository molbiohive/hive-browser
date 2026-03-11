"""Collection service -- CRUD for global enzyme/primer sets."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from hive.db.models import Collection, Part, PartInstance, PartName, User


async def list_collections(
    session: AsyncSession,
    set_type: str | None = None,
) -> list[Collection]:
    """List all collections, optionally filtered by type."""
    stmt = select(Collection)
    if set_type:
        stmt = stmt.where(Collection.set_type == set_type)
    stmt = stmt.order_by(Collection.is_default.desc(), Collection.name)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_collection(
    session: AsyncSession, collection_id: int,
) -> Collection | None:
    return (
        await session.execute(
            select(Collection).where(Collection.id == collection_id)
        )
    ).scalar_one_or_none()


async def create_collection(
    session: AsyncSession,
    name: str,
    set_type: str,
    items: list,
    is_default: bool = False,
) -> Collection:
    if set_type not in ("enzymes", "primers"):
        raise ValueError(f"Invalid set_type: {set_type}")
    col = Collection(
        name=name,
        set_type=set_type,
        items=items,
        is_default=is_default,
    )
    session.add(col)
    await session.flush()
    return col


async def update_collection(
    session: AsyncSession,
    collection_id: int,
    name: str | None = None,
    items: list | None = None,
) -> Collection:
    col = await get_collection(session, collection_id)
    if not col:
        raise ValueError(f"Collection {collection_id} not found")
    if name is not None:
        col.name = name
    if items is not None:
        col.items = items
    await session.flush()
    return col


async def delete_collection(session: AsyncSession, collection_id: int) -> bool:
    col = await get_collection(session, collection_id)
    if not col:
        return False
    await session.delete(col)
    await session.flush()
    return True


async def get_active_enzyme_names(
    session: AsyncSession, user_id: int | None,
) -> list[str] | None:
    """Return enzyme names from the user's active enzyme collection.

    Returns None if no collection is selected (meaning: use all enzymes).
    """
    if user_id is None:
        return None
    user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if not user:
        return None
    col_id = (user.preferences or {}).get("enzyme_collection_id")
    if not col_id:
        return None
    col = await get_collection(session, int(col_id))
    if not col or col.set_type != "enzymes":
        return None
    return col.items


async def get_active_primer_parts(
    session: AsyncSession, user_id: int | None,
) -> list[dict]:
    """Return primer parts from the user's active primer collection.

    Returns list of {id, name, sequence} dicts for use with find_primer_sites().
    If no collection is selected, returns all primer parts in the DB.
    """
    col_id = None
    if user_id is not None:
        user = (
            await session.execute(select(User).where(User.id == user_id))
        ).scalar_one_or_none()
        if user:
            col_id = (user.preferences or {}).get("primer_collection_id")

    if col_id:
        col = await get_collection(session, int(col_id))
        if col and col.set_type == "primers" and col.items:
            part_ids = [int(i) for i in col.items]
            stmt = (
                select(Part)
                .where(Part.id.in_(part_ids))
                .options(selectinload(Part.names))
            )
            parts = (await session.execute(stmt)).scalars().all()
            return [
                {
                    "id": p.id,
                    "name": p.names[0].name if p.names else "",
                    "sequence": p.sequence,
                }
                for p in parts
            ]

    # No collection selected -- return all primer parts
    stmt = (
        select(Part)
        .join(PartInstance, Part.id == PartInstance.part_id)
        .where(PartInstance.annotation_type == "primer_bind")
        .options(selectinload(Part.names))
        .distinct()
    )
    parts = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": p.id,
            "name": p.names[0].name if p.names else "",
            "sequence": p.sequence,
        }
        for p in parts
    ]

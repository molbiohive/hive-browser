"""Enzyme DB loading and bootstrap."""

import json
import logging
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hive.db import Collection, Enzyme

logger = logging.getLogger(__name__)

_EXTRAS_DIR = Path(__file__).resolve().parent.parent / "extras"

# Module-level cache: {UPPER_NAME: Enzyme}
_enzyme_cache: dict[str, Enzyme] | None = None


async def load_enzymes(session: AsyncSession) -> dict[str, Enzyme]:
    """Load all enzymes from DB. Cached after first call."""
    global _enzyme_cache
    if _enzyme_cache is not None:
        return _enzyme_cache
    rows = (await session.execute(select(Enzyme))).scalars().all()
    _enzyme_cache = {e.name.upper(): e for e in rows}
    return _enzyme_cache


async def bootstrap_enzymes(session: AsyncSession) -> int:
    """Load enzymes from extras/enzymes.json if DB is empty.

    Returns the number of enzymes loaded (0 if already populated).
    """
    count = (await session.execute(select(func.count()).select_from(Enzyme))).scalar() or 0
    if count > 0:
        logger.debug("Enzymes already loaded: %d", count)
        await _bootstrap_default_collection(session)
        return 0

    path = _EXTRAS_DIR / "enzymes.json"
    if not path.is_file():
        logger.warning("Enzyme data not found: %s", path)
        return 0

    raw = json.loads(path.read_text())
    items = raw.get("data", [])

    for entry in items:
        name = entry.get("name")
        if not name:
            continue
        session.add(
            Enzyme(
                name=entry["name"],
                site=entry["site"],
                cut5=entry["cut5"],
                cut3=entry["cut3"],
                overhang=entry["overhang"],
                length=entry["length"],
                is_palindrome=entry["is_palindrome"],
                is_blunt=entry["is_blunt"],
            )
        )

    await session.flush()
    loaded = len(items)
    logger.info("Bootstrapped %d enzymes from %s", loaded, path.name)

    # Bootstrap default enzyme collection
    await _bootstrap_default_collection(session)

    return loaded


_DEFAULT_ENZYMES = [
    "EcoRI",
    "BamHI",
    "HindIII",
    "XbaI",
    "SalI",
    "PstI",
    "SphI",
    "KpnI",
    "NcoI",
    "NdeI",
    "NheI",
    "XhoI",
    "NotI",
    "EcoRV",
    "SmaI",
    "SacI",
    "SacII",
    "ClaI",
    "BglII",
    "ApaI",
    "MluI",
    "StuI",
    "ScaI",
    "SpeI",
    "BsaI",
    "BbsI",
    "BsmBI",
    "SapI",
    "AarI",
    "DpnI",
]


async def _bootstrap_default_collection(session: AsyncSession) -> None:
    """Create a default 'Common Enzymes' collection if none exists."""
    existing = (
        await session.execute(
            select(func.count())
            .select_from(Collection)
            .where(Collection.set_type == "enzymes", Collection.is_default.is_(True))
        )
    ).scalar() or 0
    if existing > 0:
        return

    session.add(
        Collection(
            name="Common Enzymes",
            set_type="enzymes",
            items=_DEFAULT_ENZYMES,
            is_default=True,
        )
    )
    await session.flush()
    logger.info("Bootstrapped default enzyme collection (%d enzymes)", len(_DEFAULT_ENZYMES))

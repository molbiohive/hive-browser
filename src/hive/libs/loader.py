"""Import/export part libraries as JSON envelopes."""

import json
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hive.db.models import (
    Annotation,
    Library,
    LibraryMember,
    Part,
    PartName,
)
from hive.utils import hash_sequence

logger = logging.getLogger(__name__)


def validate_envelope(data: dict) -> tuple[str, int, list]:
    """Validate typed JSON envelope. Returns (type, version, data)."""
    if not isinstance(data, dict):
        raise ValueError("Envelope must be a JSON object")
    for field in ("type", "version", "data"):
        if field not in data:
            raise ValueError(f"Missing required field: {field}")
    typ = data["type"]
    version = data["version"]
    items = data["data"]
    if not isinstance(typ, str) or not typ:
        raise ValueError("'type' must be a non-empty string")
    if not isinstance(version, int) or version < 1:
        raise ValueError("'version' must be a positive integer")
    if not isinstance(items, list):
        raise ValueError("'data' must be a list")
    return typ, version, items


# ── Import ───────────────────────────────────────────────────────────


async def import_lib(session: AsyncSession, path: Path) -> dict:
    """Import a part library from a JSON envelope file."""
    raw = json.loads(path.read_text())
    typ, version, items = validate_envelope(raw)
    if typ != "library":
        raise ValueError(f"Expected type 'library', got '{typ}'")

    lib_name = raw.get("name")
    if not lib_name:
        raise ValueError("Library envelope requires a 'name' field")

    # Get or create library
    row = await session.execute(select(Library).where(Library.name == lib_name))
    lib = row.scalar_one_or_none()
    if not lib:
        lib = Library(
            name=lib_name,
            source="native",
            description=raw.get("description"),
        )
        session.add(lib)
        await session.flush()

    parts_created = 0
    parts_existing = 0

    for entry in items:
        sequence = entry.get("sequence", "").upper()
        if not sequence:
            continue
        molecule = entry.get("molecule", "DNA")
        seq_hash = hash_sequence(sequence)

        # Get or create Part
        row = await session.execute(select(Part).where(Part.sequence_hash == seq_hash))
        part = row.scalar_one_or_none()
        if part:
            parts_existing += 1
        else:
            part = Part(
                sequence_hash=seq_hash, sequence=sequence,
                molecule=molecule, length=len(sequence),
            )
            session.add(part)
            await session.flush()
            parts_created += 1

        # Names
        for name_entry in entry.get("names", []):
            n = name_entry if isinstance(name_entry, str) else name_entry.get("name", "")
            src = "import" if isinstance(name_entry, str) else name_entry.get("source", "import")
            if not n:
                continue
            exists = await session.execute(
                select(PartName).where(
                    PartName.part_id == part.id, PartName.name == n, PartName.source == src,
                )
            )
            if not exists.scalar_one_or_none():
                session.add(PartName(part_id=part.id, name=n, source=src))

        # Annotations
        for ann in entry.get("annotations", []):
            key, value = ann.get("key", ""), ann.get("value", "")
            ann_src = ann.get("source", "import")
            if not key:
                continue
            exists = await session.execute(
                select(Annotation).where(
                    Annotation.part_id == part.id, Annotation.key == key,
                    Annotation.value == value, Annotation.source == ann_src,
                )
            )
            if not exists.scalar_one_or_none():
                session.add(Annotation(
                    part_id=part.id, key=key, value=value, source=ann_src,
                ))

        # Library membership
        exists = await session.execute(
            select(LibraryMember).where(
                LibraryMember.library_id == lib.id, LibraryMember.part_id == part.id,
            )
        )
        if not exists.scalar_one_or_none():
            session.add(LibraryMember(library_id=lib.id, part_id=part.id))

    await session.flush()
    logger.info("Library '%s': %d created, %d existing", lib_name, parts_created, parts_existing)
    return {
        "type": "library", "name": lib_name,
        "parts_created": parts_created, "parts_existing": parts_existing,
    }


# ── Export ───────────────────────────────────────────────────────────


async def export_lib(session: AsyncSession, name: str, path: Path):
    """Export a part library by name to JSON envelope."""
    row = await session.execute(select(Library).where(Library.name == name))
    lib = row.scalar_one_or_none()
    if not lib:
        raise ValueError(f"Library not found: {name}")

    members = (await session.execute(
        select(LibraryMember).where(LibraryMember.library_id == lib.id)
    )).scalars().all()

    data = []
    for m in members:
        part = (await session.execute(
            select(Part).where(Part.id == m.part_id)
        )).scalar_one()

        names = (await session.execute(
            select(PartName).where(PartName.part_id == part.id)
        )).scalars().all()

        annotations = (await session.execute(
            select(Annotation).where(Annotation.part_id == part.id)
        )).scalars().all()

        data.append({
            "sequence": part.sequence,
            "molecule": part.molecule,
            "names": [{"name": n.name, "source": n.source} for n in names],
            "annotations": [
                {"key": a.key, "value": a.value, "source": a.source}
                for a in annotations
            ],
        })

    envelope = {
        "type": "library", "version": 1,
        "name": lib.name, "source": lib.source,
        "description": lib.description, "data": data,
    }
    path.write_text(json.dumps(envelope, indent=2) + "\n")
    logger.info("Exported library '%s' (%d parts) to %s", name, len(data), path)

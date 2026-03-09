"""Knowledge engine -- annotation intelligence for Hive Browser."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hive.db.models import Annotation, Library, LibraryMember
from hive.libs.classify import classify_part

logger = logging.getLogger(__name__)

# Annotation type -> native library name.
# Auto-created during ingest. Each maps a GenBank/SnapGene feature type
# to a named library using Library (source="native") + LibraryMember.
NATIVE_LIBRARY_MAP = {
    # Coding
    "CDS": "CDS",
    "gene": "Genes",
    # Regulatory
    "promoter": "Promoters",
    "terminator": "Terminators",
    "enhancer": "Enhancers",
    "RBS": "RBS",
    "regulatory": "Regulatory",
    # Structural
    "rep_origin": "Origins",
    "sig_peptide": "Signal Peptides",
    "transit_peptide": "Transit Peptides",
    "mat_peptide": "Mature Peptides",
    # Primers
    "primer_bind": "Primers",
    # Non-coding RNA
    "ncRNA": "ncRNA",
    # Repeats & mobile elements
    "repeat_region": "Repeats",
    "LTR": "LTR",
    "mobile_element": "Mobile Elements",
    # Binding sites
    "protein_bind": "Protein Binding",
    "misc_binding": "Binding Sites",
    # UTRs
    "5'UTR": "5' UTRs",
    "3'UTR": "3' UTRs",
    # Catch-all
    "misc_feature": "Misc",
}


async def add_annotation(
    session: AsyncSession, part_id: int, key: str, value: str, source: str,
):
    """Add annotation if not already present."""
    existing = await session.execute(
        select(Annotation).where(
            Annotation.part_id == part_id,
            Annotation.key == key,
            Annotation.value == value,
            Annotation.source == source,
        )
    )
    if not existing.scalar_one_or_none():
        session.add(Annotation(
            part_id=part_id, key=key, value=value, source=source,
        ))


async def get_or_create_library(
    session: AsyncSession, name: str, source: str = "native",
) -> Library:
    """Get or create a library by name."""
    existing = await session.execute(
        select(Library).where(Library.name == name)
    )
    lib = existing.scalar_one_or_none()
    if lib:
        return lib
    lib = Library(name=name, source=source)
    session.add(lib)
    await session.flush()
    return lib


async def tag_libraries(
    session: AsyncSession, part_id: int, annotation_type: str,
):
    """Add part to native library matching its annotation type."""
    lib_name = NATIVE_LIBRARY_MAP.get(annotation_type)
    if not lib_name:
        return
    lib = await get_or_create_library(session, lib_name, source="native")
    existing = await session.execute(
        select(LibraryMember).where(
            LibraryMember.library_id == lib.id,
            LibraryMember.part_id == part_id,
        )
    )
    if not existing.scalar_one_or_none():
        session.add(LibraryMember(library_id=lib.id, part_id=part_id))


async def annotate_part(
    session: AsyncSession,
    part_id: int,
    annotation_type: str,
    sequence: str,
    molecule: str = "DNA",
):
    """Store type annotation and run classify_part() to add computed annotations."""
    await add_annotation(session, part_id, "type", annotation_type, source="native")

    # Run deterministic classification
    props = classify_part(sequence, annotation_type, molecule)
    for key, value in props.items():
        await add_annotation(session, part_id, key, value, source="computed")

    # Auto-tag into native libraries
    await tag_libraries(session, part_id, annotation_type)

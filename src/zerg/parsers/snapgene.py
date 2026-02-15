"""SnapGene .dna file parser using sgffp."""

from pathlib import Path

from zerg.parsers.base import ParsedFeature, ParsedPrimer, ParseResult


def parse_snapgene(filepath: Path, extract: list[str] | None = None) -> ParseResult:
    """Parse a SnapGene .dna file and return structured data."""
    from sgffp import SgffReader

    sgff = SgffReader.from_file(filepath)

    features = []
    if extract is None or "features" in extract:
        for f in sgff.features:
            features.append(ParsedFeature(
                name=f.name,
                type=f.type,
                start=f.start,
                end=f.end,
                strand=f.strand,
                qualifiers=dict(f.qualifiers) if hasattr(f, "qualifiers") else {},
            ))

    primers = []
    if extract is None or "primers" in extract:
        for p in sgff.primers:
            primers.append(ParsedPrimer(
                name=p.name,
                sequence=p.sequence,
                tm=getattr(p, "tm", None),
                start=getattr(p, "start", None),
                end=getattr(p, "end", None),
                strand=getattr(p, "strand", None),
            ))

    meta = {}
    if extract is None or "notes" in extract:
        if hasattr(sgff, "notes") and sgff.notes:
            meta["notes"] = sgff.notes

    return ParseResult(
        name=filepath.stem,
        sequence=sgff.sequence.value,
        size_bp=len(sgff.sequence.value),
        topology=sgff.sequence.topology,
        description=meta.get("notes"),
        features=features,
        primers=primers,
        meta=meta,
    )

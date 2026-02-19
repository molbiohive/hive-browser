"""SnapGene file parser using sgffp (.dna, .rna, .prot)."""

from pathlib import Path

from zerg.parsers.base import ParsedFeature, ParsedPrimer, ParseResult

# sgffp block IDs → molecule type
_BLOCK_MOLECULE_TYPE = {0: "DNA", 1: "DNA", 21: "protein", 32: "RNA"}

# sgffp strand strings → integer (DB stores SmallInteger)
_STRAND_MAP = {"+": 1, "-": -1, ".": 0, "1": 1, "-1": -1}


def _parse_strand(strand) -> int:
    if isinstance(strand, int):
        return strand
    return _STRAND_MAP.get(str(strand), 0)


def parse_snapgene(filepath: Path, extract: list[str] | None = None) -> ParseResult:
    """Parse a SnapGene file (.dna, .rna, .prot) and return structured data."""
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
                strand=_parse_strand(f.strand),
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
                strand=(
                    _parse_strand(getattr(p, "strand", None))
                    if getattr(p, "strand", None) is not None
                    else None
                ),
            ))

    meta = {}
    if (
        (extract is None or "notes" in extract)
        and hasattr(sgff, "notes")
        and sgff.notes
        and sgff.notes.exists
    ):
        meta["notes"] = sgff.notes.data

    molecule_type = _BLOCK_MOLECULE_TYPE.get(sgff.sequence.block_id, "DNA")
    meta["molecule_type"] = molecule_type

    description = None
    if hasattr(sgff, "notes") and sgff.notes and sgff.notes.exists:
        desc = sgff.notes.description
        if desc:
            description = desc

    return ParseResult(
        name=filepath.stem,
        sequence=sgff.sequence.value,
        size_bp=len(sgff.sequence.value),
        topology=sgff.sequence.topology,
        description=description,
        features=features,
        primers=primers,
        meta=meta,
    )

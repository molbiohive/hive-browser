"""GenBank .gb/.gbk parser using Biopython."""

from pathlib import Path

from Bio import SeqIO

from hive.parsers.base import ParsedFeature, ParseResult


def parse_genbank(filepath: Path, extract: list[str] | None = None) -> ParseResult:
    """Parse a GenBank file and return structured data."""
    record = SeqIO.read(str(filepath), "genbank")

    features = []
    if extract is None or "features" in extract:
        for f in record.features:
            if f.type == "source":
                continue
            features.append(ParsedFeature(
                name=(f.qualifiers.get("label") or f.qualifiers.get("gene") or [f.type])[0],
                type=f.type,
                start=int(f.location.start),
                end=int(f.location.end),
                strand=f.location.strand or 1,
                qualifiers={k: v[0] if isinstance(v, list) else v
                            for k, v in f.qualifiers.items()},
            ))

    # Detect molecule type from GenBank annotations
    mol_type = record.annotations.get("molecule_type", "")
    if "protein" in mol_type.lower():
        molecule = "protein"
    elif "rna" in mol_type.lower():
        molecule = "RNA"
    else:
        molecule = "DNA"

    return ParseResult(
        name=record.name,
        sequence=str(record.seq),
        size_bp=len(record.seq),
        topology=record.annotations.get("topology", "linear"),
        molecule=molecule,
        description=record.description if record.description != "." else None,
        features=features,
        meta={},
    )

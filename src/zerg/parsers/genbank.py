"""GenBank .gb/.gbk parser using Biopython."""

from pathlib import Path

from Bio import SeqIO

from zerg.parsers.base import ParsedFeature, ParseResult


def parse_genbank(filepath: Path, extract: list[str] | None = None) -> ParseResult:
    """Parse a GenBank file and return structured data."""
    record = SeqIO.read(str(filepath), "genbank")

    features = []
    if extract is None or "features" in extract:
        for f in record.features:
            if f.type == "source":
                continue
            features.append(ParsedFeature(
                name=f.qualifiers.get("label", [f.qualifiers.get("gene", [f.type])])[0],
                type=f.type,
                start=int(f.location.start),
                end=int(f.location.end),
                strand=f.location.strand or 1,
                qualifiers={k: v[0] if isinstance(v, list) else v
                            for k, v in f.qualifiers.items()},
            ))

    return ParseResult(
        name=record.name,
        sequence=str(record.seq),
        size_bp=len(record.seq),
        topology=record.annotations.get("topology", "linear"),
        description=record.description if record.description != "." else None,
        features=features,
        meta={},
    )

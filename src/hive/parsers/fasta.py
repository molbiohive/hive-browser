"""FASTA parser using Biopython."""

from pathlib import Path

from Bio import SeqIO

from hive.parsers.base import ParseResult


def parse_fasta(filepath: Path, extract: list[str] | None = None) -> ParseResult:
    """Parse a FASTA file and return structured data (sequence only)."""
    record = SeqIO.read(str(filepath), "fasta")

    return ParseResult(
        name=record.id,
        sequence=str(record.seq),
        size_bp=len(record.seq),
        topology="linear",
        description=record.description if record.description != record.id else None,
        meta={},
    )

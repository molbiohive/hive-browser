"""FASTA parser using Biopython."""

from pathlib import Path

from Bio import SeqIO

from hive.parsers.base import ParseResult
from hive.utils import detect_molecule


def parse_fasta(filepath: Path, extract: list[str] | None = None) -> ParseResult:
    """Parse a FASTA file and return structured data (sequence only)."""
    record = SeqIO.read(str(filepath), "fasta")
    seq_str = str(record.seq)

    return ParseResult(
        name=record.id,
        sequence=seq_str,
        size_bp=len(record.seq),
        topology="linear",
        molecule=detect_molecule(seq_str),
        description=record.description if record.description != record.id else None,
        meta={},
    )

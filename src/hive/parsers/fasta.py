"""FASTA parser -- native implementation, no Biopython."""

from pathlib import Path

from hive.parsers.base import ParseResult
from hive.utils import detect_molecule


def parse_fasta(filepath: Path, extract: list[str] | None = None) -> ParseResult:
    """Parse a FASTA file and return structured data (sequence only)."""
    text = filepath.read_text()
    lines = text.strip().splitlines()

    # First line starting with '>' is the header
    name = filepath.stem
    description = None
    seq_lines = []

    for line in lines:
        line = line.strip()
        if line.startswith(">"):
            # Parse header: >id description
            header = line[1:].strip()
            parts = header.split(None, 1)
            name = parts[0] if parts else filepath.stem
            if len(parts) > 1:
                description = parts[1]
        elif line:
            seq_lines.append(line)

    seq_str = "".join(seq_lines)

    return ParseResult(
        name=name,
        sequence=seq_str,
        size_bp=len(seq_str),
        topology="linear",
        molecule=detect_molecule(seq_str),
        description=description,
        meta={},
    )

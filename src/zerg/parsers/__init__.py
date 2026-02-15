"""File parsers — registry maps parser name to implementation."""

from zerg.parsers.base import ParseResult
from zerg.parsers.fasta import parse_fasta
from zerg.parsers.genbank import parse_genbank
from zerg.parsers.snapgene import parse_snapgene

PARSERS = {
    "sgffp": parse_snapgene,
    "biopython": parse_genbank,  # default biopython parser
}

# Format-specific overrides when parser is 'biopython'
BIOPYTHON_PARSERS = {
    "gb": parse_genbank,
    "gbk": parse_genbank,
    "fasta": parse_fasta,
    "fa": parse_fasta,
}

__all__ = ["PARSERS", "BIOPYTHON_PARSERS", "ParseResult"]

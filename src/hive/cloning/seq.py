"""Pure sequence operations -- no Biopython."""

import json
from pathlib import Path

from hive.cloning.enzymes import _COMPLEMENT

_EXTRAS_DIR = Path(__file__).resolve().parent.parent / "extras"

# Module-level cache for codon tables
_codon_tables: dict[int, dict] | None = None


def _load_codon_tables() -> dict[int, dict]:
    """Load and cache codon tables from extras/codon_tables.json."""
    global _codon_tables
    if _codon_tables is not None:
        return _codon_tables
    path = _EXTRAS_DIR / "codon_tables.json"
    raw = json.loads(path.read_text())
    _codon_tables = {t["id"]: t for t in raw["data"]}
    return _codon_tables


def reverse_complement(seq: str) -> str:
    """Reverse complement of a DNA sequence (IUPAC-aware)."""
    return seq.upper().translate(_COMPLEMENT)[::-1]


def transcribe(seq: str) -> str:
    """Transcribe DNA to RNA (T -> U)."""
    return seq.upper().replace("T", "U")


def back_transcribe(seq: str) -> str:
    """Back-transcribe RNA to DNA (U -> T)."""
    return seq.upper().replace("U", "T")


def translate(seq: str, table: int = 1) -> str:
    """Translate a DNA/RNA sequence to protein.

    Loads codon table from extras/codon_tables.json (cached).
    Trailing incomplete codons are ignored.
    Stop codons are translated as '*'.
    """
    seq = seq.upper().replace("U", "T")
    tables = _load_codon_tables()
    ct = tables.get(table)
    if ct is None:
        raise ValueError(f"Unknown codon table: {table}")

    forward = ct["forward_table"]
    stops = set(ct["stop_codons"])
    protein = []
    for i in range(0, len(seq) - 2, 3):
        codon = seq[i:i + 3]
        if codon in stops:
            protein.append("*")
        elif codon in forward:
            protein.append(forward[codon])
        else:
            protein.append("X")  # unknown codon
    return "".join(protein)

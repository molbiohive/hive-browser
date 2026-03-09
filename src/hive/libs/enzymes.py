"""IUPAC cut site scanner -- no Biopython dependency."""

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hive.db.models import Enzyme

# IUPAC ambiguity codes -> regex character classes
IUPAC_MAP = {
    "R": "[AG]", "Y": "[CT]", "W": "[AT]", "S": "[GC]",
    "M": "[AC]", "K": "[GT]", "B": "[CGT]", "D": "[AGT]",
    "H": "[ACT]", "V": "[ACG]", "N": "[ACGT]",
}

_COMPLEMENT = str.maketrans("ACGTRYWSMKBDHVN", "TGCAYRWSKMVHDBN")

# Module-level cache: {UPPER_NAME: Enzyme}
_enzyme_cache: dict[str, Enzyme] | None = None


def _site_to_regex(site: str) -> re.Pattern:
    """Convert IUPAC recognition site to compiled regex."""
    parts = []
    for ch in site.upper():
        if ch in IUPAC_MAP:
            parts.append(IUPAC_MAP[ch])
        elif ch in "ACGT":
            parts.append(ch)
        else:
            raise ValueError(f"Invalid IUPAC character: {ch}")
    return re.compile("".join(parts))


def _reverse_complement(seq: str) -> str:
    """Reverse complement of a DNA sequence (IUPAC-aware)."""
    return seq.upper().translate(_COMPLEMENT)[::-1]


async def load_enzymes(session: AsyncSession) -> dict[str, Enzyme]:
    """Load all enzymes from DB. Cached after first call."""
    global _enzyme_cache
    if _enzyme_cache is not None:
        return _enzyme_cache
    rows = (await session.execute(select(Enzyme))).scalars().all()
    _enzyme_cache = {e.name.upper(): e for e in rows}
    return _enzyme_cache


def clear_cache():
    """Clear the enzyme cache (for testing or after import)."""
    global _enzyme_cache
    _enzyme_cache = None


@dataclass
class CutSite:
    """A single cut site on the sequence."""
    position: int     # 0-based position of the cut on the sense strand
    enzyme: str       # enzyme name
    strand: int       # +1 sense, -1 antisense (for non-palindromic)


def find_cut_sites(
    sequence: str,
    enzyme_names: list[str],
    enzymes: dict[str, Enzyme],
    circular: bool = True,
) -> dict:
    """Find restriction enzyme cut sites in a sequence.

    Returns dict with:
        enzyme_results: per-enzyme breakdown
        all_cuts: sorted unique cut positions
        total_cuts: count
        fragments: sorted fragment sizes (descending)
        seq_len: sequence length
        circular: topology flag
    """
    sequence = sequence.upper()
    seq_len = len(sequence)

    # For circular sequences, extend to catch wrap-around matches
    if circular:
        search_seq = sequence + sequence
    else:
        search_seq = sequence

    enzyme_results = []
    all_cuts: list[int] = []

    for name in enzyme_names:
        enz = enzymes.get(name.upper())
        if not enz:
            raise ValueError(f"Unknown enzyme: {name}")

        pattern = _site_to_regex(enz.site)
        sites: list[int] = []

        # Search sense strand
        for m in pattern.finditer(search_seq):
            pos = m.start() + enz.cut5
            if 0 <= pos < seq_len:
                sites.append(pos)
            elif circular and pos >= seq_len:
                sites.append(pos % seq_len)

        # Non-palindromic: also search reverse complement
        if not enz.is_palindrome:
            rc_site = _reverse_complement(enz.site)
            rc_pattern = _site_to_regex(rc_site)
            for m in rc_pattern.finditer(search_seq):
                # Sense strand cut position for antisense recognition
                pos = m.start() - enz.cut3
                if 0 <= pos < seq_len:
                    sites.append(pos)
                elif circular and pos >= seq_len:
                    sites.append(pos % seq_len)

        sites = sorted(set(sites))
        enzyme_results.append({
            "name": enz.name,
            "sites": sites,
            "num_cuts": len(sites),
        })
        all_cuts.extend(sites)

    all_cuts = sorted(set(all_cuts))
    total_cuts = len(all_cuts)

    # Calculate fragments
    if total_cuts == 0:
        fragments = [seq_len]
    elif circular:
        frags = []
        for i in range(total_cuts):
            if i + 1 < total_cuts:
                frags.append(all_cuts[i + 1] - all_cuts[i])
            else:
                frags.append(seq_len - all_cuts[i] + all_cuts[0])
        fragments = sorted(frags, reverse=True)
    else:
        frags = [all_cuts[0]]
        for i in range(1, total_cuts):
            frags.append(all_cuts[i] - all_cuts[i - 1])
        frags.append(seq_len - all_cuts[-1])
        fragments = sorted(frags, reverse=True)

    return {
        "enzyme_results": enzyme_results,
        "all_cuts": all_cuts,
        "total_cuts": total_cuts,
        "fragments": fragments,
        "seq_len": seq_len,
        "circular": circular,
    }

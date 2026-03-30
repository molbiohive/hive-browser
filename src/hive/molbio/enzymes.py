"""IUPAC cut site scanner -- pure algorithms, no DB dependency."""

import re

from hive.molbio.seq import reverse_complement

# IUPAC ambiguity codes -> regex character classes
IUPAC_MAP = {
    "R": "[AG]",
    "Y": "[CT]",
    "W": "[AT]",
    "S": "[GC]",
    "M": "[AC]",
    "K": "[GT]",
    "B": "[CGT]",
    "D": "[AGT]",
    "H": "[ACT]",
    "V": "[ACG]",
    "N": "[ACGT]",
}


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


def find_cut_sites(
    sequence: str,
    enzyme_names: list[str],
    enzymes: dict,
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
            rc_site = reverse_complement(enz.site)
            rc_pattern = _site_to_regex(rc_site)
            for m in rc_pattern.finditer(search_seq):
                # Sense strand cut position for antisense recognition
                pos = m.start() - enz.cut3
                if 0 <= pos < seq_len:
                    sites.append(pos)
                elif circular and pos >= seq_len:
                    sites.append(pos % seq_len)

        sites = sorted(set(sites))
        enzyme_results.append(
            {
                "name": enz.name,
                "sites": sites,
                "num_cuts": len(sites),
            }
        )
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


def find_all_cutters(
    sequence: str,
    enzymes: dict,
    circular: bool = True,
    max_cuts: int | None = None,
) -> list[dict]:
    """Scan sequence against ALL enzymes. Return those that cut.

    If max_cuts is set, only return enzymes with <= max_cuts sites
    (e.g. max_cuts=1 for unique cutters).
    Returns list of {name, site, num_cuts, positions} sorted by num_cuts asc.
    """
    sequence = sequence.upper()
    seq_len = len(sequence)
    search_seq = sequence + sequence if circular else sequence

    cutters = []
    for enz in enzymes.values():
        pattern = _site_to_regex(enz.site)
        positions: list[int] = []

        for m in pattern.finditer(search_seq):
            pos = m.start()
            if 0 <= pos < seq_len:
                positions.append(pos)
            elif circular and pos >= seq_len:
                positions.append(pos % seq_len)

        if not enz.is_palindrome:
            rc_site = reverse_complement(enz.site)
            rc_pattern = _site_to_regex(rc_site)
            for m in rc_pattern.finditer(search_seq):
                pos = m.start()
                if 0 <= pos < seq_len:
                    positions.append(pos)
                elif circular and pos >= seq_len:
                    positions.append(pos % seq_len)

        positions = sorted(set(positions))
        if not positions:
            continue
        if max_cuts is not None and len(positions) > max_cuts:
            continue
        cutters.append(
            {
                "name": enz.name,
                "site": enz.site,
                "num_cuts": len(positions),
                "positions": positions,
            }
        )

    cutters.sort(key=lambda x: x["num_cuts"])
    return cutters

"""Codon usage analysis -- pure functions, no DB."""

from hive.molbio.seq import _load_codon_tables


def codon_usage(seq: str, table: int = 1) -> list[dict]:
    """Calculate codon usage statistics.

    Returns list of {codon, amino_acid, count, frequency, rscu} dicts.
    RSCU = Relative Synonymous Codon Usage.
    """
    seq = seq.upper().replace("U", "T")
    tables = _load_codon_tables()
    ct = tables.get(table)
    if ct is None:
        raise ValueError(f"Unknown codon table: {table}")

    forward = ct["forward_table"]
    stops = set(ct["stop_codons"])

    # Count codons
    counts: dict[str, int] = {}
    for i in range(0, len(seq) - 2, 3):
        codon = seq[i : i + 3]
        if len(codon) == 3:
            counts[codon] = counts.get(codon, 0) + 1

    # Build amino acid -> codon groups
    aa_codons: dict[str, list[str]] = {}
    for codon, aa in forward.items():
        aa_codons.setdefault(aa, []).append(codon)
    for stop in stops:
        aa_codons.setdefault("*", []).append(stop)

    # Calculate RSCU: count / (average count for synonymous codons)
    result = []
    total_codons = sum(counts.values())
    for codon in sorted(forward.keys()):
        aa = forward[codon]
        count = counts.get(codon, 0)
        freq = count / total_codons if total_codons > 0 else 0.0

        # RSCU = observed / expected (if all synonymous used equally)
        synonymous = aa_codons.get(aa, [codon])
        syn_total = sum(counts.get(c, 0) for c in synonymous)
        n_syn = len(synonymous)
        expected = syn_total / n_syn if n_syn > 0 else 0
        rscu = count / expected if expected > 0 else 0.0

        result.append({
            "codon": codon,
            "amino_acid": aa,
            "count": count,
            "frequency": round(freq, 4),
            "rscu": round(rscu, 2),
        })

    # Add stop codons
    for codon in sorted(stops):
        count = counts.get(codon, 0)
        freq = count / total_codons if total_codons > 0 else 0.0
        synonymous = aa_codons.get("*", [])
        syn_total = sum(counts.get(c, 0) for c in synonymous)
        n_syn = len(synonymous)
        expected = syn_total / n_syn if n_syn > 0 else 0
        rscu = count / expected if expected > 0 else 0.0
        result.append({
            "codon": codon,
            "amino_acid": "*",
            "count": count,
            "frequency": round(freq, 4),
            "rscu": round(rscu, 2),
        })

    return result


def rare_codons(seq: str, table: int = 1, threshold: float = 0.15) -> list[dict]:
    """Return codons with frequency below threshold.

    Only includes codons that actually appear in the sequence.
    """
    usage = codon_usage(seq, table)
    return [
        entry for entry in usage
        if entry["count"] > 0 and entry["frequency"] < threshold and entry["amino_acid"] != "*"
    ]

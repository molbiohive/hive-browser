"""Primer binding site prediction -- 3' anchor scanning."""

from __future__ import annotations

from hive.cloning.enzymes import _COMPLEMENT


def _reverse_complement(seq: str) -> str:
    return seq.upper().translate(_COMPLEMENT)[::-1]


def find_primer_sites(
    sequence: str,
    primers: list[dict],
    circular: bool = True,
    anchor_len: int = 10,
) -> list[dict]:
    """Predict primer binding sites on a target sequence.

    For each primer, takes the last *anchor_len* bases (3' end) and scans:
    - Sense strand for anchor match -> forward binding (strand=1)
    - Sense strand for RC of anchor -> reverse binding (strand=-1)

    For circular sequences, searches seq+seq and takes positions modulo len.

    Args:
        sequence: Target DNA sequence.
        primers: List of dicts with keys: id, name, sequence.
        circular: Whether the target is circular.
        anchor_len: Number of 3'-end bases to use as anchor.

    Returns:
        List of binding site dicts:
        {primer_id, name, start, end, strand, primer_length}
    """
    seq = sequence.upper()
    seq_len = len(seq)
    if seq_len == 0:
        return []

    search_seq = seq + seq if circular else seq
    results: list[dict] = []

    for primer in primers:
        primer_seq = primer.get("sequence", "").upper()
        if not primer_seq or len(primer_seq) < anchor_len:
            continue

        anchor = primer_seq[-anchor_len:]
        rc_anchor = _reverse_complement(anchor)
        primer_len = len(primer_seq)
        primer_id = primer.get("id")
        primer_name = primer.get("name", "")

        # Forward binding: anchor found on sense strand
        start = 0
        while True:
            pos = search_seq.find(anchor, start)
            if pos == -1:
                break
            # Anchor matches at the 3' end of the primer binding site
            bind_end = pos + anchor_len
            bind_start = bind_end - primer_len
            # Normalize position for circular
            norm_start = bind_start % seq_len if circular else bind_start
            if 0 <= bind_start and (pos < seq_len or circular):
                actual_start = norm_start if circular and pos >= seq_len else bind_start
                if actual_start < seq_len:
                    results.append({
                        "primer_id": primer_id,
                        "name": primer_name,
                        "start": actual_start,
                        "end": (actual_start + primer_len) % seq_len if circular else actual_start + primer_len,
                        "strand": 1,
                        "primer_length": primer_len,
                        "primer_sequence": primer_seq,
                    })
            start = pos + 1

        # Reverse binding: RC of anchor found on sense strand
        start = 0
        while True:
            pos = search_seq.find(rc_anchor, start)
            if pos == -1:
                break
            # RC anchor at the 5' end of the reverse-complement binding site
            bind_start = pos
            bind_end = pos + primer_len
            norm_start = bind_start % seq_len if circular else bind_start
            if pos < seq_len or circular:
                actual_start = norm_start if circular and pos >= seq_len else bind_start
                if actual_start < seq_len:
                    results.append({
                        "primer_id": primer_id,
                        "name": primer_name,
                        "start": actual_start,
                        "end": (actual_start + primer_len) % seq_len if circular else actual_start + primer_len,
                        "strand": -1,
                        "primer_length": primer_len,
                        "primer_sequence": primer_seq,
                    })
            start = pos + 1

    # Deduplicate (same primer_id + start + strand)
    seen: set[tuple] = set()
    unique: list[dict] = []
    for r in results:
        key = (r["primer_id"], r["start"], r["strand"])
        if key not in seen:
            seen.add(key)
            unique.append(r)

    return unique

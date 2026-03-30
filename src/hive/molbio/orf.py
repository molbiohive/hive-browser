"""6-frame ORF scanner -- pure functions, no DB."""

from hive.molbio.seq import reverse_complement, translate

_START_CODONS = {"ATG"}
_STOP_CODONS = {"TAA", "TAG", "TGA"}


def find_orfs(seq: str, min_length: int = 100) -> list[dict]:
    """Scan all 6 reading frames for ORFs.

    Args:
        seq: DNA sequence.
        min_length: Minimum ORF length in nucleotides.

    Returns:
        List of ORF dicts sorted by length_nt descending:
        {frame, start, end, length_nt, length_aa, protein, has_start, has_stop, status}
    """
    seq = seq.upper().replace("U", "T")
    rc = reverse_complement(seq)
    orfs: list[dict] = []

    for strand_seq, strand_label in [(seq, "+"), (rc, "-")]:
        for frame_offset in range(3):
            frame_name = f"{strand_label}{frame_offset + 1}"
            orfs.extend(
                _scan_frame(strand_seq, frame_offset, frame_name, min_length, strand_label, len(seq))
            )

    orfs.sort(key=lambda x: x["length_nt"], reverse=True)
    return orfs


def _scan_frame(
    seq: str,
    offset: int,
    frame: str,
    min_length: int,
    strand: str,
    seq_len: int,
) -> list[dict]:
    """Scan one reading frame for ORFs between start and stop codons."""
    results: list[dict] = []
    codons = []
    for i in range(offset, len(seq) - 2, 3):
        codons.append((i, seq[i : i + 3]))

    # Find all ORFs: start codon to stop codon
    i = 0
    while i < len(codons):
        pos, codon = codons[i]
        if codon in _START_CODONS:
            # Found a start -- scan to next stop
            orf_start = pos
            orf_codons = [codon]
            j = i + 1
            found_stop = False
            while j < len(codons):
                _, c = codons[j]
                orf_codons.append(c)
                if c in _STOP_CODONS:
                    found_stop = True
                    orf_end = codons[j][0] + 3
                    break
                j += 1
            else:
                # Ran off the end -- partial ORF
                orf_end = codons[-1][0] + 3

            length_nt = orf_end - orf_start
            if length_nt >= min_length:
                orf_seq = seq[orf_start:orf_end]
                protein = translate(orf_seq)
                # Map coordinates back to original strand
                if strand == "+":
                    report_start = orf_start
                    report_end = orf_end
                else:
                    report_start = seq_len - orf_end
                    report_end = seq_len - orf_start

                results.append({
                    "frame": frame,
                    "start": report_start,
                    "end": report_end,
                    "length_nt": length_nt,
                    "length_aa": len(protein.rstrip("*")),
                    "protein": protein,
                    "has_start": True,
                    "has_stop": found_stop,
                    "status": "complete" if found_stop else "no_stop",
                })

            if found_stop:
                i = j + 1
            else:
                break
        else:
            i += 1

    return results

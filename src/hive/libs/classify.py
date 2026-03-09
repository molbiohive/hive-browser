"""Deterministic part classification -- pure functions, no DB, no async."""

import math

# Standard genetic code (NCBI table 1)
_START_CODONS = {"ATG"}
_STOP_CODONS = {"TAA", "TAG", "TGA"}


def gc_content(sequence: str) -> float:
    """GC content as a fraction (0.0-1.0). Returns 0.0 for empty sequences."""
    seq = sequence.upper()
    if not seq:
        return 0.0
    gc = sum(1 for c in seq if c in "GC")
    return gc / len(seq)


def analyze_orf(sequence: str) -> dict[str, str]:
    """Analyze CDS/ORF properties. Returns string-valued annotations."""
    seq = sequence.upper()
    result: dict[str, str] = {}

    if len(seq) < 3:
        result["orf_status"] = "too_short"
        return result

    has_start = seq[:3] in _START_CODONS
    has_stop = len(seq) >= 3 and seq[-3:] in _STOP_CODONS

    result["has_start"] = str(has_start).lower()
    result["has_stop"] = str(has_stop).lower()

    # Count codons (full triplets only)
    codon_count = len(seq) // 3
    result["codon_count"] = str(codon_count)

    # Check for internal stop codons (exclude last codon)
    internal_stops = 0
    for i in range(0, (codon_count - 1) * 3, 3):
        codon = seq[i : i + 3]
        if codon in _STOP_CODONS:
            internal_stops += 1
    result["internal_stops"] = str(internal_stops)

    # ORF status
    if has_start and has_stop and internal_stops == 0:
        result["orf_status"] = "complete"
    elif has_start and not has_stop:
        result["orf_status"] = "no_stop"
    elif not has_start and has_stop:
        result["orf_status"] = "no_start"
    elif not has_start and not has_stop:
        result["orf_status"] = "partial"
    else:
        # has_start and has_stop but has internal stops
        result["orf_status"] = "internal_stops"

    # In-frame check
    result["in_frame"] = str(len(seq) % 3 == 0).lower()

    return result


def _tm_wallace(seq: str) -> float:
    """Wallace rule Tm for oligonucleotides <=13 nt."""
    at = sum(1 for c in seq if c in "AT")
    gc = sum(1 for c in seq if c in "GC")
    return 2.0 * at + 4.0 * gc


def _tm_salt_adjusted(seq: str) -> float:
    """Salt-adjusted Tm for oligonucleotides >13 nt (50 mM Na+)."""
    n = len(seq)
    gc = sum(1 for c in seq if c in "GC")
    gc_frac = gc / n if n > 0 else 0.0
    # Bolton & McCarthy (1962), adjusted for salt
    return 64.9 + 41.0 * (gc - 16.4) / n


def analyze_primer(sequence: str) -> dict[str, str]:
    """Analyze primer properties. Returns string-valued annotations."""
    seq = sequence.upper()
    result: dict[str, str] = {}

    n = len(seq)
    if n == 0:
        return result

    gc_frac = gc_content(seq)
    result["gc_content"] = f"{gc_frac:.3f}"

    if n <= 13:
        tm = _tm_wallace(seq)
    else:
        tm = _tm_salt_adjusted(seq)
    result["tm"] = f"{tm:.1f}"

    return result


def classify_part(
    sequence: str,
    annotation_type: str,
    molecule: str = "DNA",
) -> dict[str, str]:
    """Classify a part based on its sequence and annotation type.

    Returns a dict of string key-value pairs suitable for Annotation storage.
    All values are strings to match the Annotation.value column type.
    """
    seq = sequence.upper()
    result: dict[str, str] = {}

    # Universal properties
    result["length"] = str(len(seq))
    result["gc_content"] = f"{gc_content(seq):.3f}"

    # Type-specific analysis
    if annotation_type == "CDS":
        result.update(analyze_orf(seq))
    elif annotation_type == "primer_bind":
        result.update(analyze_primer(seq))

    return result

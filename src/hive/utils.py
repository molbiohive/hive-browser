"""Shared utility functions."""

import hashlib

# Amino acid characters that never appear in nucleotide sequences
_AA_ONLY = set("EFIJLOPQZX*")


def hash_sequence(seq: str) -> str:
    """SHA256 of uppercased sequence string."""
    return hashlib.sha256(seq.upper().encode()).hexdigest()


def detect_molecule(seq: str, meta: dict | None = None) -> str:
    """Detect molecule type from sequence + metadata hints.

    Returns "DNA", "RNA", or "protein".
    """
    if meta:
        mol = meta.get("molecule_type", "")
        if mol in ("DNA", "RNA", "protein"):
            return mol

    upper = seq.upper()
    if any(c in _AA_ONLY for c in upper):
        return "protein"
    if "U" in upper and "T" not in upper:
        return "RNA"
    return "DNA"

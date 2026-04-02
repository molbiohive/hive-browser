"""Shared utility functions."""

import hashlib
import time
from contextlib import contextmanager

# Amino acid characters that never appear in nucleotide sequences
_AA_ONLY = set("EFIJLOPQZX*")


def hash_sequence(seq: str) -> str:
    """SHA256 of uppercased sequence string."""
    return hashlib.sha256(seq.upper().encode()).hexdigest()


def format_elapsed(seconds: float) -> str:
    """Format seconds into human-friendly string: '1.2s', '2m 15s', '1h 3m'."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}h {mins}m"


class Stopwatch:
    """Lightweight timer for measuring elapsed time."""

    def __init__(self):
        self._start = time.monotonic()
        self.elapsed: float = 0.0

    def stop(self) -> float:
        self.elapsed = time.monotonic() - self._start
        return self.elapsed

    def __str__(self) -> str:
        return format_elapsed(self.elapsed)


@contextmanager
def timed():
    """Context manager that measures elapsed time.

    Usage::

        with timed() as t:
            do_work()
        print(f"Done in {t}")  # "Done in 12.3s"
    """
    sw = Stopwatch()
    yield sw
    sw.stop()


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

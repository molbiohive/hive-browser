"""ProtParam-style protein analysis -- pure functions, no DB."""

import json
import math
from pathlib import Path

_EXTRAS_DIR = Path(__file__).resolve().parents[3] / "extras"

# Lazy-loaded amino acid residue weights
_residue_weights: dict[str, float] | None = None
_water_weight: float = 18.0153


def _load_weights() -> tuple[dict[str, float], float]:
    """Load amino acid molecular weights from extras/molecular_weights.json."""
    global _residue_weights, _water_weight
    if _residue_weights is not None:
        return _residue_weights, _water_weight
    path = _EXTRAS_DIR / "molecular_weights.json"
    raw = json.loads(path.read_text())
    _residue_weights = raw["data"]["amino_acid_residues"]
    _water_weight = raw["data"]["water"]
    return _residue_weights, _water_weight


# pKa values for ionizable groups (EMBOSS defaults)
_PK_N_TERM = 8.6
_PK_C_TERM = 3.6
_PK_SIDE: dict[str, float] = {
    "D": 3.9,  # Asp
    "E": 4.1,  # Glu
    "C": 8.3,  # Cys
    "Y": 10.1,  # Tyr
    "H": 6.0,  # His
    "K": 10.5,  # Lys
    "R": 12.5,  # Arg
}

# Positive at low pH
_POSITIVE_GROUPS = {"H", "K", "R"}
# Negative at high pH
_NEGATIVE_GROUPS = {"D", "E", "C", "Y"}

# Kyte-Doolittle hydropathy scale
_KD_HYDROPATHY: dict[str, float] = {
    "A": 1.8, "C": 2.5, "D": -3.5, "E": -3.5, "F": 2.8,
    "G": -0.4, "H": -3.2, "I": 4.5, "K": -3.9, "L": 3.8,
    "M": 1.9, "N": -3.5, "P": -1.6, "Q": -3.5, "R": -4.5,
    "S": -0.8, "T": -0.7, "V": 4.2, "W": -0.9, "Y": -1.3,
}

# Guruprasad instability dipeptide weight values (DIWV)
# From: Guruprasad et al. (1990) Protein Engineering 4(2):155-161
_DIWV: dict[str, dict[str, float]] = {
    "W": {"C": 1.0, "W": 1.0, "E": 1.0, "D": 1.0, "G": -9.2, "A": -14.2, "L": 13.34, "M": 24.68, "F": 1.0, "H": 24.68, "I": 1.0, "K": 1.0, "N": 13.34, "P": 1.0, "Q": 1.0, "R": 1.0, "S": 1.0, "T": -14.03, "V": -7.49, "Y": 1.0},
    "C": {"W": 24.68, "C": 1.0, "E": 1.0, "D": 20.26, "G": 1.0, "A": 1.0, "L": 20.26, "M": 33.6, "F": 1.0, "H": 33.6, "I": 1.0, "K": 1.0, "N": 1.0, "P": 20.26, "Q": -6.54, "R": 1.0, "S": 1.0, "T": 33.6, "V": -6.54, "Y": 1.0},
    "E": {"W": -14.03, "C": 44.94, "E": 33.6, "D": 20.26, "G": 1.0, "A": 1.0, "L": 1.0, "M": 1.0, "F": 1.0, "H": -6.54, "I": 20.26, "K": 1.0, "N": 1.0, "P": 20.26, "Q": 20.26, "R": 1.0, "S": 20.26, "T": 1.0, "V": 1.0, "Y": 1.0},
    "D": {"W": 1.0, "C": 1.0, "E": 1.0, "D": 1.0, "G": 1.0, "A": 1.0, "L": 1.0, "M": 1.0, "F": -6.54, "H": 1.0, "I": 1.0, "K": -7.49, "N": 1.0, "P": 1.0, "Q": 1.0, "R": -6.54, "S": 20.26, "T": -14.03, "V": 1.0, "Y": 1.0},
    "G": {"W": 13.34, "C": 1.0, "E": -6.54, "D": 1.0, "G": 13.34, "A": -7.49, "L": 1.0, "M": 1.0, "F": 1.0, "H": 1.0, "I": -7.49, "K": -7.49, "N": -7.49, "P": 1.0, "Q": 1.0, "R": 1.0, "S": 1.0, "T": -7.49, "V": 1.0, "Y": -7.49},
    "A": {"W": 1.0, "C": 44.94, "E": 1.0, "D": -7.49, "G": 1.0, "A": 1.0, "L": 1.0, "M": 1.0, "F": 1.0, "H": -7.49, "I": 1.0, "K": 1.0, "N": 1.0, "P": 20.26, "Q": 1.0, "R": 1.0, "S": 1.0, "T": 1.0, "V": 1.0, "Y": 1.0},
    "L": {"W": 24.68, "C": 1.0, "E": 1.0, "D": 1.0, "G": 1.0, "A": 1.0, "L": 1.0, "M": 1.0, "F": 1.0, "H": 1.0, "I": 1.0, "K": -7.49, "N": 1.0, "P": 20.26, "Q": 33.6, "R": 20.26, "S": 1.0, "T": 1.0, "V": 1.0, "Y": 1.0},
    "M": {"W": 1.0, "C": 1.0, "E": 1.0, "D": 1.0, "G": 1.0, "A": 13.34, "L": 1.0, "M": -1.88, "F": 1.0, "H": 58.28, "I": 1.0, "K": 1.0, "N": 1.0, "P": 44.94, "Q": -6.54, "R": -6.54, "S": 44.94, "T": -1.88, "V": 1.0, "Y": 24.68},
    "F": {"W": 1.0, "C": 1.0, "E": 1.0, "D": 13.34, "G": 1.0, "A": 1.0, "L": 1.0, "M": 1.0, "F": 1.0, "H": 1.0, "I": 1.0, "K": -14.03, "N": 1.0, "P": 20.26, "Q": 1.0, "R": 1.0, "S": 1.0, "T": 1.0, "V": 1.0, "Y": 33.6},
    "H": {"W": -1.88, "C": 1.0, "E": 1.0, "D": 1.0, "G": -9.2, "A": 1.0, "L": -1.88, "M": 1.0, "F": -9.2, "H": 1.0, "I": 44.94, "K": 24.68, "N": 24.68, "P": -1.88, "Q": 1.0, "R": 1.0, "S": 1.0, "T": -6.54, "V": 1.0, "Y": 44.94},
    "I": {"W": 1.0, "C": 1.0, "E": 44.94, "D": 1.0, "G": 1.0, "A": 1.0, "L": 20.26, "M": 1.0, "F": 1.0, "H": 13.34, "I": 1.0, "K": -7.49, "N": 1.0, "P": -1.88, "Q": 1.0, "R": 1.0, "S": 1.0, "T": 1.0, "V": -7.49, "Y": 1.0},
    "K": {"W": 1.0, "C": 1.0, "E": 1.0, "D": 1.0, "G": -7.49, "A": 1.0, "L": -7.49, "M": 33.6, "F": 1.0, "H": 1.0, "I": -7.49, "K": 1.0, "N": 1.0, "P": -6.54, "Q": 24.64, "R": 33.6, "S": 1.0, "T": 1.0, "V": -7.49, "Y": 1.0},
    "N": {"W": -9.37, "C": -1.88, "E": 1.0, "D": 1.0, "G": -14.03, "A": 1.0, "L": 1.0, "M": 1.0, "F": -14.03, "H": 1.0, "I": 44.94, "K": 24.68, "N": 1.0, "P": -1.88, "Q": -6.54, "R": 1.0, "S": 1.0, "T": -7.49, "V": 1.0, "Y": 1.0},
    "P": {"W": -1.88, "C": -6.54, "E": 18.38, "D": -6.54, "G": 1.0, "A": 20.26, "L": 1.0, "M": -6.54, "F": 20.26, "H": 1.0, "I": 1.0, "K": 1.0, "N": 1.0, "P": 20.26, "Q": 20.26, "R": -6.54, "S": 20.26, "T": 1.0, "V": 20.26, "Y": 1.0},
    "Q": {"W": 1.0, "C": -6.54, "E": 20.26, "D": 20.26, "G": 1.0, "A": 1.0, "L": 1.0, "M": 1.0, "F": -6.54, "H": 1.0, "I": 1.0, "K": 1.0, "N": 1.0, "P": 20.26, "Q": 20.26, "R": 1.0, "S": 44.94, "T": 1.0, "V": -6.54, "Y": 1.0},
    "R": {"W": 58.28, "C": 1.0, "E": 1.0, "D": 1.0, "G": -7.49, "A": 1.0, "L": 1.0, "M": 1.0, "F": 1.0, "H": 20.26, "I": 1.0, "K": 1.0, "N": 13.34, "P": 20.26, "Q": 20.26, "R": 58.28, "S": 44.94, "T": 1.0, "V": 1.0, "Y": -6.54},
    "S": {"W": 1.0, "C": 33.6, "E": 20.26, "D": 1.0, "G": 1.0, "A": 1.0, "L": 1.0, "M": 1.0, "F": 1.0, "H": 1.0, "I": 1.0, "K": 1.0, "N": 1.0, "P": 44.94, "Q": 20.26, "R": 20.26, "S": 20.26, "T": 1.0, "V": 1.0, "Y": 1.0},
    "T": {"W": -14.03, "C": 1.0, "E": 20.26, "D": 1.0, "G": -7.49, "A": 1.0, "L": 1.0, "M": 1.0, "F": 13.34, "H": 1.0, "I": 1.0, "K": 1.0, "N": -14.03, "P": 1.0, "Q": -6.54, "R": 1.0, "S": 1.0, "T": 1.0, "V": 1.0, "Y": 1.0},
    "V": {"W": 1.0, "C": 1.0, "E": 1.0, "D": -14.03, "G": -7.49, "A": 1.0, "L": 1.0, "M": 1.0, "F": 1.0, "H": 1.0, "I": 1.0, "K": -1.88, "N": 1.0, "P": 20.26, "Q": 1.0, "R": 1.0, "S": 1.0, "T": -7.49, "V": 1.0, "Y": -6.54},
    "Y": {"W": -9.37, "C": 1.0, "E": -6.54, "D": 24.68, "G": -7.49, "A": 24.68, "L": 1.0, "M": 44.94, "F": 1.0, "H": 13.34, "I": 1.0, "K": 1.0, "N": 1.0, "P": 13.34, "Q": 1.0, "R": -15.91, "S": 1.0, "T": -7.49, "V": 1.0, "Y": 13.34},
}

# Amino acid full names
_AA_NAMES: dict[str, str] = {
    "A": "Alanine", "C": "Cysteine", "D": "Aspartate", "E": "Glutamate",
    "F": "Phenylalanine", "G": "Glycine", "H": "Histidine", "I": "Isoleucine",
    "K": "Lysine", "L": "Leucine", "M": "Methionine", "N": "Asparagine",
    "P": "Proline", "Q": "Glutamine", "R": "Arginine", "S": "Serine",
    "T": "Threonine", "V": "Valine", "W": "Tryptophan", "Y": "Tyrosine",
}


def _strip_protein(seq: str) -> str:
    """Uppercase and strip trailing stop codon."""
    seq = seq.upper()
    if seq.endswith("*"):
        seq = seq[:-1]
    return seq


def molecular_weight(seq: str) -> float:
    """Calculate protein molecular weight in Daltons."""
    seq = _strip_protein(seq)
    weights, water = _load_weights()
    mw = sum(weights.get(aa, 0.0) for aa in seq)
    # Subtract water for each peptide bond
    mw -= water * (len(seq) - 1)
    return round(mw, 2)


def charge_at_ph(seq: str, ph: float = 7.0) -> float:
    """Net charge at given pH using Henderson-Hasselbalch equation."""
    seq = _strip_protein(seq)
    charge = 0.0

    # N-terminus (positive)
    charge += 1.0 / (1.0 + 10 ** (ph - _PK_N_TERM))
    # C-terminus (negative)
    charge -= 1.0 / (1.0 + 10 ** (_PK_C_TERM - ph))

    for aa in seq:
        pk = _PK_SIDE.get(aa)
        if pk is None:
            continue
        if aa in _POSITIVE_GROUPS:
            charge += 1.0 / (1.0 + 10 ** (ph - pk))
        else:
            charge -= 1.0 / (1.0 + 10 ** (pk - ph))

    return round(charge, 2)


def isoelectric_point(seq: str) -> float:
    """Estimate pI by bisection search."""
    lo, hi = 0.0, 14.0
    for _ in range(100):
        mid = (lo + hi) / 2.0
        c = charge_at_ph(seq, mid)
        if c > 0:
            lo = mid
        else:
            hi = mid
        if abs(c) < 0.001:
            break
    return round((lo + hi) / 2.0, 2)


def amino_acid_composition(seq: str) -> list[dict]:
    """Return table-ready amino acid composition."""
    seq = _strip_protein(seq)
    n = len(seq)
    counts: dict[str, int] = {}
    for aa in seq:
        counts[aa] = counts.get(aa, 0) + 1

    result = []
    for aa in sorted(_AA_NAMES.keys()):
        count = counts.get(aa, 0)
        result.append({
            "amino_acid": aa,
            "name": _AA_NAMES[aa],
            "count": count,
            "percent": round(count / n * 100, 1) if n > 0 else 0.0,
        })
    return result


def extinction_coefficient(seq: str) -> dict:
    """Molar extinction coefficient at 280nm (Pace et al., 1995).

    Returns {reduced, oxidized} in M^-1 cm^-1.
    """
    seq = _strip_protein(seq)
    n_trp = seq.count("W")
    n_tyr = seq.count("Y")
    n_cys = seq.count("C")

    # Pace et al. (1995) coefficients
    e_reduced = n_trp * 5500 + n_tyr * 1490
    e_oxidized = e_reduced + (n_cys // 2) * 125

    return {"reduced": e_reduced, "oxidized": e_oxidized}


def gravy(seq: str) -> float:
    """Grand average of hydropathy (GRAVY) using Kyte-Doolittle scale."""
    seq = _strip_protein(seq)
    if not seq:
        return 0.0
    total = sum(_KD_HYDROPATHY.get(aa, 0.0) for aa in seq)
    return round(total / len(seq), 3)


def instability_index(seq: str) -> float:
    """Instability index (Guruprasad et al., 1990).

    A protein with II > 40 is predicted to be unstable.
    """
    seq = _strip_protein(seq)
    n = len(seq)
    if n < 2:
        return 0.0
    total = 0.0
    for i in range(n - 1):
        aa1 = seq[i]
        aa2 = seq[i + 1]
        row = _DIWV.get(aa1)
        if row:
            total += row.get(aa2, 1.0)
        else:
            total += 1.0
    return round(10.0 / n * total, 2)

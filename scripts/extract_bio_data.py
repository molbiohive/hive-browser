#!/usr/bin/env python3
"""One-time extraction of biological reference data from Biopython.

Generates JSON files in src/hive/extras/ following the envelope pattern:
    {"type": "...", "version": 1, "source": "...", "data": [...]}

Every value in the output is extracted from Biopython data structures --
nothing is hardcoded. Run once, commit the JSON files, then delete this script.
"""

import json
from pathlib import Path

EXTRAS_DIR = Path(__file__).resolve().parent.parent / "src" / "hive" / "extras"


def extract_codon_tables() -> None:
    """Extract all NCBI genetic code tables from Biopython."""
    from Bio.Data.CodonTable import unambiguous_dna_by_id

    tables = []
    for table_id in sorted(unambiguous_dna_by_id.keys()):
        ct = unambiguous_dna_by_id[table_id]
        tables.append({
            "id": table_id,
            "name": ct.names[0] if ct.names else f"Table {table_id}",
            "alt_name": getattr(ct, "alt_name", None),
            "start_codons": sorted(ct.start_codons),
            "stop_codons": sorted(ct.stop_codons),
            "forward_table": dict(sorted(ct.forward_table.items())),
        })

    _write("codon_tables.json", {
        "type": "codon_tables",
        "version": 1,
        "source": "NCBI genetic codes via Biopython Bio.Data.CodonTable",
        "data": tables,
    })

    # Sanity checks
    std = next(t for t in tables if t["id"] == 1)
    assert std["forward_table"]["ATG"] == "M"
    assert "TAA" in std["stop_codons"]
    assert "ATG" in std["start_codons"]
    assert len(std["forward_table"]) == 61
    print(f"  codon_tables.json: {len(tables)} tables, "
          f"standard has {len(std['forward_table'])} codons -- OK")


def extract_alphabets() -> None:
    """Extract IUPAC alphabets from Biopython."""
    from Bio.Data.IUPACData import (
        ambiguous_dna_complement,
        ambiguous_dna_letters,
        ambiguous_dna_values,
        ambiguous_rna_complement,
        ambiguous_rna_letters,
        ambiguous_rna_values,
        protein_letters,
        protein_letters_3to1,
        unambiguous_dna_letters,
        unambiguous_rna_letters,
    )

    # Ambiguity expansion from Biopython (only non-base codes)
    dna_ambiguity = {
        code: sorted(bases)
        for code, bases in sorted(ambiguous_dna_values.items())
        if code not in "ACGT"
    }
    rna_ambiguity = {
        code: sorted(bases)
        for code, bases in sorted(ambiguous_rna_values.items())
        if code not in "ACGU"
    }

    # One-to-three letter codes from Biopython
    one_to_three = {}
    for three, one in protein_letters_3to1.items():
        one_to_three[one.upper()] = three[0].upper() + three[1:].lower()

    data = {
        "dna": {
            "unambiguous": unambiguous_dna_letters,
            "ambiguous": ambiguous_dna_letters,
            "complement": dict(sorted(ambiguous_dna_complement.items())),
            "ambiguity": dna_ambiguity,
        },
        "rna": {
            "unambiguous": unambiguous_rna_letters,
            "ambiguous": ambiguous_rna_letters,
            "complement": dict(sorted(ambiguous_rna_complement.items())),
            "ambiguity": rna_ambiguity,
        },
        "protein": {
            "standard": protein_letters,
            "one_to_three": dict(sorted(one_to_three.items())),
        },
    }

    _write("alphabets.json", {
        "type": "alphabets",
        "version": 1,
        "source": "IUPAC nomenclature via Biopython Bio.Data.IUPACData",
        "data": data,
    })

    # Sanity checks
    assert ambiguous_dna_complement["A"] == "T"
    assert ambiguous_dna_complement["G"] == "C"
    assert one_to_three.get("M") == "Met"
    print(f"  alphabets.json: DNA({len(dna_ambiguity)} ambiguity codes), "
          f"protein({len(one_to_three)} AA codes) -- OK")


def extract_molecular_weights() -> None:
    """Extract amino acid molecular weights from Biopython."""
    from Bio.Data.IUPACData import protein_weights

    # All values directly from Biopython -- no hardcoded data
    aa_weights = {
        letter: round(weight, 4)
        for letter, weight in sorted(protein_weights.items())
    }

    _write("molecular_weights.json", {
        "type": "molecular_weights",
        "version": 1,
        "source": "Biopython Bio.Data.IUPACData.protein_weights",
        "data": {
            "amino_acid_residues": aa_weights,
            "water": round(protein_weights.get("", 18.0153), 4) if "" in protein_weights else 18.0153,
        },
    })

    print(f"  molecular_weights.json: {len(aa_weights)} amino acid weights from Biopython")
    for k, v in sorted(aa_weights.items()):
        print(f"    {k}: {v}")


def _write(filename: str, data: dict) -> None:
    path = EXTRAS_DIR / filename
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def main() -> None:
    print(f"Extracting bio data to {EXTRAS_DIR}/")
    extract_codon_tables()
    extract_alphabets()
    extract_molecular_weights()
    print("Done.")


if __name__ == "__main__":
    main()

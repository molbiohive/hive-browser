"""ProtParam tool -- protein physicochemical properties."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from hive.molbio.protein import (
    amino_acid_composition,
    charge_at_ph,
    extinction_coefficient,
    gravy,
    instability_index,
    isoelectric_point,
    molecular_weight,
)
from hive.molbio.seq import translate as seq_translate
from hive.tools.base import Tool
from hive.tools.resolve import resolve_and_clean

_DNA_RE = re.compile(r"^[ACGTUN]+$", re.IGNORECASE)


class ProtparamInput(BaseModel):
    sequence: str = Field(
        ...,
        description="Protein sequence, DNA/RNA sequence (auto-translated), or sid:N/pid:N",
    )
    table: int = Field(default=1, description="Codon table for translation (if DNA input)")


class ProtparamTool(Tool):
    name = "protparam"
    description = ("protein properties", "Physicochemical properties of a protein: MW, pI, GRAVY, instability, extinction coefficient, amino acid composition.")
    tags = {"analysis"}
    advanced = {"table"}

    def __init__(self, **_):
        pass

    def input_schema(self) -> dict:
        schema = ProtparamInput.model_json_schema()
        schema.pop("title", None)
        return schema

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        inp = ProtparamInput(**params)
        result = await resolve_and_clean(inp.sequence)
        if isinstance(result, dict):
            return result
        cleaned, _meta = result

        # Auto-detect DNA/RNA and translate
        if _DNA_RE.match(cleaned):
            if len(cleaned) < 3:
                return {"error": "Sequence too short to translate"}
            dna = cleaned.replace("U", "T")
            protein = seq_translate(dna, table=inp.table)
            if protein.endswith("*"):
                protein = protein[:-1]
        else:
            protein = cleaned.rstrip("*")

        if not protein:
            return {"error": "Empty protein sequence"}

        mw = molecular_weight(protein)
        pi = isoelectric_point(protein)
        charge = charge_at_ph(protein, 7.0)
        ec = extinction_coefficient(protein)
        g = gravy(protein)
        ii = instability_index(protein)
        comp = amino_acid_composition(protein)

        return {
            "protein": protein,
            "length": len(protein),
            "properties": [
                {"property": "Molecular weight", "value": mw, "unit": "Da"},
                {"property": "Isoelectric point", "value": pi, "unit": "pH"},
                {"property": "Charge at pH 7", "value": charge, "unit": ""},
                {"property": "Extinction coefficient (reduced)", "value": ec["reduced"], "unit": "M-1 cm-1"},
                {"property": "Extinction coefficient (oxidized)", "value": ec["oxidized"], "unit": "M-1 cm-1"},
                {"property": "GRAVY", "value": g, "unit": ""},
                {"property": "Instability index", "value": ii, "unit": ""},
                {"property": "Predicted stability", "value": "stable" if ii < 40 else "unstable", "unit": ""},
            ],
            "composition": comp,
        }

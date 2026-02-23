"""Digest tool — restriction enzyme digestion analysis."""

from __future__ import annotations

from typing import Any

from Bio.Seq import Seq
from pydantic import BaseModel, Field

from hive.tools.base import Tool


class DigestInput(BaseModel):
    sequence: str = Field(..., description="Nucleotide sequence to digest")
    enzymes: list[str] = Field(..., description='Enzyme names, e.g. ["EcoRI", "BamHI"]')
    circular: bool = Field(
        default=True,
        description="True for circular (plasmid), False for linear",
    )


class DigestTool(Tool):
    name = "digest"
    description = "Find restriction enzyme cut sites and calculate fragment sizes."
    widget = "text"
    tags = {"llm", "analysis"}
    guidelines = "Restriction digest. Provide enzymes list and sequence."

    def __init__(self, **_):
        pass

    def input_schema(self) -> dict:
        schema = DigestInput.model_json_schema()
        schema.pop("title", None)
        return schema

    def format_result(self, result: dict) -> str:
        if error := result.get("error"):
            return f"Error: {error}"
        cuts = result.get("total_cuts", 0)
        frags = result.get("fragments", [])
        return f"{cuts} cut(s), {len(frags)} fragment(s): {frags}"

    def summary_for_llm(self, result: dict) -> str:
        if error := result.get("error"):
            return f"Error: {error}"
        enzymes = result.get("enzymes", [])
        parts = []
        for e in enzymes:
            parts.append(f"{e['name']}: {e['num_cuts']} cut(s) at {e['sites']}")
        frags = result.get("fragments", [])
        return "; ".join(parts) + f". Fragments: {frags}"

    async def execute(self, params: dict[str, Any], mode: str = "direct") -> dict[str, Any]:
        inp = DigestInput(**params)
        cleaned = inp.sequence.upper().replace(" ", "").replace("\n", "")

        if len(cleaned) < 1:
            return {"error": "Empty sequence"}

        # Lazy import — Bio.Restriction is large
        try:
            from Bio.Restriction import RestrictionBatch
        except ImportError:
            return {"error": "Bio.Restriction not available"}

        # Validate enzyme names
        try:
            rb = RestrictionBatch(inp.enzymes)
        except (ValueError, KeyError) as e:
            return {"error": f"Invalid enzyme name: {e}"}

        seq_obj = Seq(cleaned)
        results = rb.search(seq_obj, linear=not inp.circular)

        enzyme_results = []
        all_cuts = []
        for enzyme, sites in sorted(results.items(), key=lambda x: str(x[0])):
            enzyme_results.append({
                "name": str(enzyme),
                "sites": sites,
                "num_cuts": len(sites),
            })
            all_cuts.extend(sites)

        # Calculate fragment sizes
        all_cuts = sorted(set(all_cuts))
        total_cuts = len(all_cuts)
        seq_len = len(cleaned)

        if total_cuts == 0:
            fragments = [seq_len]
        elif inp.circular:
            frags = []
            for i in range(len(all_cuts)):
                if i + 1 < len(all_cuts):
                    frags.append(all_cuts[i + 1] - all_cuts[i])
                else:
                    frags.append(seq_len - all_cuts[i] + all_cuts[0])
            fragments = sorted(frags, reverse=True)
        else:
            frags = [all_cuts[0]]
            for i in range(1, len(all_cuts)):
                frags.append(all_cuts[i] - all_cuts[i - 1])
            frags.append(seq_len - all_cuts[-1])
            fragments = sorted(frags, reverse=True)

        return {
            "enzymes": enzyme_results,
            "fragments": fragments,
            "total_cuts": total_cuts,
            "sequence_length": seq_len,
            "circular": inp.circular,
        }

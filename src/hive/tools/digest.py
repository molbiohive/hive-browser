"""Digest tool — restriction enzyme digestion analysis."""

from __future__ import annotations

from typing import Any

from Bio.Seq import Seq
from pydantic import BaseModel, Field

from hive.db import session as db
from hive.tools.base import Tool
from hive.tools.resolve import resolve_input


class DigestInput(BaseModel):
    sequence: str = Field(..., description="DNA sequence, or sid:N for Sequence ID, or pid:N for Part ID")
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
    guidelines = "Restriction digest. Provide enzymes list and sequence (or sid:N / pid:N)."

    def __init__(self, **_):
        pass

    def input_schema(self) -> dict:
        schema = DigestInput.model_json_schema()
        schema.pop("title", None)
        return schema

    def llm_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "sequence": {"type": "string", "description": "DNA sequence, sid:N, or pid:N"},
                "enzymes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Enzyme names",
                },
            },
            "required": ["sequence", "enzymes"],
        }

    def format_result(self, result: dict) -> str:
        if error := result.get("error"):
            return f"Error: {error}"
        cuts = result.get("total_cuts", 0)
        frags = result.get("fragments", [])
        return f"{cuts} cut(s), {len(frags)} fragment(s): {frags}"

    async def execute(self, params: dict[str, Any], mode: str = "direct") -> dict[str, Any]:
        inp = DigestInput(**params)
        seq = inp.sequence
        if seq.strip().lower().startswith(("sid:", "pid:")) and db.async_session_factory:
            async with db.async_session_factory() as session:
                try:
                    seq, _meta = await resolve_input(session, seq)
                except ValueError as exc:
                    return {"error": str(exc)}
        cleaned = seq.upper().replace(" ", "").replace("\n", "")

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
        except (ValueError, KeyError):
            return {"error": f"Unknown enzyme(s): {', '.join(inp.enzymes)}"}

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

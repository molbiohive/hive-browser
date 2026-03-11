"""Examine tool -- close-up interactive view of a sequence."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from hive.config import display_file_path
from hive.context import current_user_id
from hive.db import session as db
from hive.tools.base import Tool
from hive.tools.resolve import resolve_sequence

logger = logging.getLogger(__name__)


def _dedup_primers(primers: list[dict]) -> list[dict]:
    """Deduplicate primers by (name, start). File-native entries come first."""
    seen: set[tuple] = set()
    out: list[dict] = []
    for p in primers:
        key = (p.get("name", ""), p.get("start"))
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


class ExamineInput(BaseModel):
    sid: int | None = Field(default=None, description="Sequence ID (preferred)")
    name: str | None = Field(default=None, description="Sequence name (fallback)")


class ExamineTool(Tool):
    name = "examine"
    description = (
        "Close-up interactive view of a sequence with plasmid map "
        "and annotated sequence viewer."
    )
    widget = "examine"
    tags = {"llm", "visual"}
    guidelines = (
        "Use ONLY when the user asks for a close-up or visual inspection "
        "of a specific sequence. Displays an interactive viewer."
    )

    def __init__(self, **_):
        pass

    def input_schema(self) -> dict:
        schema = ExamineInput.model_json_schema()
        schema.pop("title", None)
        return schema

    def llm_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "sid": {"type": "integer", "description": "Sequence ID"},
            },
            "required": ["sid"],
        }

    def format_result(self, result: dict) -> str:
        if error := result.get("error"):
            return f"Error: {error}"
        seq = result.get("sequence")
        if not seq:
            return "Sequence not found."
        return f"Displayed close-up view for {seq['name']}."

    def llm_summary(self, result: dict) -> str | None:
        """Minimal summary -- prevent raw sequence/feature data in LLM context."""
        if result.get("error"):
            return f"Error: {result['error']}"
        seq = result.get("sequence")
        if not seq:
            return "Sequence not found."
        return (
            f"Close-up view displayed for {seq['name']} "
            f"({seq['size_bp']} bp, {seq['topology']}). "
            f"No data to report."
        )

    async def execute(self, params: dict[str, Any], mode: str = "direct") -> dict[str, Any]:
        inp = ExamineInput(**params)

        if inp.sid is None and not inp.name:
            return {"error": "Provide either sid or name"}

        if not db.async_session_factory:
            return {"error": "Database unavailable"}

        async with db.async_session_factory() as session:
            seq = await resolve_sequence(
                session,
                sid=inp.sid,
                name=inp.name,
                load_parts=True,
                load_file=True,
            )

            if not seq:
                return {"error": f"Sequence not found: {inp.sid or inp.name}"}

            parts_list = [
                {
                    "pid": pi.part.id,
                    "name": pi.part.names[0].name if pi.part.names else "",
                    "annotation_type": pi.annotation_type,
                    "start": pi.start,
                    "end": pi.end,
                    "strand": pi.strand,
                    "length": pi.part.length,
                    "sequence": pi.part.sequence,
                    "qualifiers": pi.qualifiers,
                }
                for pi in seq.part_instances
            ]

            circular = seq.topology == "circular"

            # Scan cut sites (optionally filtered by active enzyme collection)
            cut_sites: list[dict] = []
            if seq.sequence and seq.molecule in (None, "DNA", "dna"):
                try:
                    from hive.cloning.collections import get_active_enzyme_names
                    from hive.cloning.enzymes import (
                        find_all_cutters,
                        find_cut_sites,
                        load_enzymes,
                    )

                    enzymes = await load_enzymes(session)
                    user_id = current_user_id.get()
                    active_names = await get_active_enzyme_names(session, user_id)

                    if active_names:
                        result = find_cut_sites(
                            seq.sequence.upper(), active_names, enzymes,
                            circular=circular,
                        )
                        for er in result["enzyme_results"]:
                            enz = enzymes.get(er["name"].upper())
                            if not enz:
                                continue
                            for pos in er["sites"]:
                                cut_sites.append({
                                    "enzyme": er["name"],
                                    "position": pos,
                                    "end": pos + enz.length,
                                    "strand": 1,
                                    "cutPosition": enz.cut5,
                                    "complementCutPosition": enz.cut3,
                                    "overhang": (
                                        "5'" if enz.overhang < 0
                                        else ("3'" if enz.overhang > 0 else "blunt")
                                    ),
                                })
                    else:
                        cutters = find_all_cutters(
                            seq.sequence.upper(), enzymes, circular=circular,
                        )
                        for c in cutters:
                            enz = enzymes.get(c["name"].upper())
                            if not enz:
                                continue
                            for pos in c["positions"]:
                                cut_sites.append({
                                    "enzyme": c["name"],
                                    "position": pos,
                                    "end": pos + enz.length,
                                    "strand": 1,
                                    "cutPosition": enz.cut5,
                                    "complementCutPosition": enz.cut3,
                                    "overhang": (
                                        "5'" if enz.overhang < 0
                                        else ("3'" if enz.overhang > 0 else "blunt")
                                    ),
                                })
                except Exception as e:
                    logger.warning("Cut site scan failed: %s", e)

            # Predict primer binding from collection
            predicted_primers: list[dict] = []
            if seq.sequence and seq.molecule in (None, "DNA", "dna"):
                try:
                    from hive.cloning.collections import get_active_primer_parts
                    from hive.cloning.primers import find_primer_sites

                    user_id = current_user_id.get()
                    primer_parts = await get_active_primer_parts(session, user_id)
                    if primer_parts:
                        predicted_primers = find_primer_sites(
                            seq.sequence.upper(), primer_parts, circular=circular,
                        )
                except Exception as e:
                    logger.warning("Primer prediction failed: %s", e)

            return {
                "sequence": {
                    "sid": seq.id,
                    "name": seq.name,
                    "size_bp": seq.length,
                    "topology": seq.topology,
                    "molecule": seq.molecule,
                    "description": seq.description,
                    "meta": seq.meta,
                    "sequence_data": seq.sequence,
                },
                "features": [
                    {
                        "pid": p["pid"],
                        "name": p["name"],
                        "type": p["annotation_type"],
                        "start": p["start"],
                        "end": p["end"],
                        "strand": p["strand"],
                        "qualifiers": p["qualifiers"],
                    }
                    for p in parts_list
                    if p["annotation_type"] != "primer_bind"
                ],
                "primers": _dedup_primers(
                    [
                        {
                            "pid": p["pid"],
                            "name": p["name"],
                            "start": p["start"],
                            "end": p["end"],
                            "strand": p["strand"],
                            "length": p["length"],
                            "sequence": p.get("sequence"),
                            "source": "file",
                        }
                        for p in parts_list
                        if p["annotation_type"] == "primer_bind"
                    ] + [
                        {
                            "pid": pp["primer_id"],
                            "name": pp["name"],
                            "start": pp["start"],
                            "end": pp["end"],
                            "strand": pp["strand"],
                            "length": pp["primer_length"],
                            "sequence": pp.get("primer_sequence"),
                            "source": "predicted",
                        }
                        for pp in predicted_primers
                    ]
                ),
                "cut_sites": cut_sites,
                "file": {
                    "path": display_file_path(seq.file.file_path),
                    "format": seq.file.format,
                    "size": seq.file.file_size,
                    "indexed_at": seq.file.indexed_at.isoformat() if seq.file.indexed_at else None,
                },
            }

"""Profile tool — full details of a single sequence."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from hive.config import display_file_path
from hive.db import session as db
from hive.tools.base import Tool
from hive.tools.resolve import resolve_sequence

logger = logging.getLogger(__name__)


class ProfileInput(BaseModel):
    sid: int | None = Field(default=None, description="Sequence ID (preferred)")
    name: str | None = Field(default=None, description="Sequence name (fallback)")


class ProfileTool(Tool):
    name = "profile"
    description = (
        "Show full details of a specific sequence: "
        "metadata, parts (features, primers), file info."
    )
    widget = "profile"
    tags = {"llm", "info"}
    guidelines = "Full sequence details. Use sid (from search results) or name."

    def __init__(self, **_):
        pass

    def input_schema(self) -> dict:
        schema = ProfileInput.model_json_schema()
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
        return f"{seq['name']} — {seq['size_bp']} bp, {seq['topology']}"

    async def execute(self, params: dict[str, Any], mode: str = "direct") -> dict[str, Any]:
        """Fetch complete sequence profile from the database."""
        inp = ProfileInput(**params)

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

            # Build parts list with pid and names
            parts_list = [
                {
                    "pid": pi.part.id,
                    "names": [n.name for n in pi.part.names],
                    "name": pi.part.names[0].name if pi.part.names else "",
                    "annotation_type": pi.annotation_type,
                    "start": pi.start,
                    "end": pi.end,
                    "strand": pi.strand,
                    "length": pi.part.length,
                    "molecule": pi.part.molecule,
                    "qualifiers": pi.qualifiers,
                }
                for pi in seq.part_instances
            ]

            # Scan for restriction cut sites
            cut_sites: list[dict] = []
            if seq.sequence and seq.molecule in (None, "DNA", "dna"):
                try:
                    from hive.cloning.enzymes import find_all_cutters, load_enzymes

                    enzymes = await load_enzymes(session)
                    circular = seq.topology == "circular"
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
                "primers": [
                    {
                        "pid": p["pid"],
                        "name": p["name"],
                        "start": p["start"],
                        "end": p["end"],
                        "strand": p["strand"],
                        "length": p["length"],
                    }
                    for p in parts_list
                    if p["annotation_type"] == "primer_bind"
                ],
                "cut_sites": cut_sites,
                "file": {
                    "path": display_file_path(seq.file.file_path),
                    "format": seq.file.format,
                    "size": seq.file.file_size,
                    "indexed_at": seq.file.indexed_at.isoformat() if seq.file.indexed_at else None,
                },
            }

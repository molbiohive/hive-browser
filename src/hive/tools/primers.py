"""Primers tool -- show primer binding sites on a sequence."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from hive.context import current_user_id
from hive.db import session as db
from hive.libs.classify import analyze_primer
from hive.tools.base import Tool
from hive.tools.resolve import dedup_primers, resolve_input, resolve_sequence

logger = logging.getLogger(__name__)


class PrimersInput(BaseModel):
    sequence: str = Field(description="Raw DNA sequence, sid:N, or pid:N")
    circular: bool = Field(default=True, description="Treat sequence as circular")


class PrimersTool(Tool):
    name = "primers"
    description = "Show primer binding sites on a sequence."
    tags = {"analysis"}
    guidelines = "Show primer binding sites on a sequence. Use sid:N or pid:N."

    def __init__(self, **_):
        pass

    def input_schema(self) -> dict:
        schema = PrimersInput.model_json_schema()
        schema.pop("title", None)
        return schema

    def llm_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "sequence": {
                    "type": "string",
                    "description": "Raw DNA sequence, sid:N, or pid:N",
                },
            },
            "required": ["sequence"],
        }

    def format_result(self, result: dict) -> str:
        if error := result.get("error"):
            return f"Error: {error}"
        name = result.get("sequence_name", "")
        count = result.get("primers_found", 0)
        return f"{name}: {count} primer(s) found" if name else f"{count} primer(s) found"

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        inp = PrimersInput(**params)

        if not db.async_session_factory:
            return {"error": "Database unavailable"}

        async with db.async_session_factory() as session:
            # Resolve input sequence
            try:
                seq_str, meta = await resolve_input(session, inp.sequence)
            except ValueError as e:
                return {"error": str(e)}

            if not seq_str:
                return {"error": "Empty sequence"}

            seq_name = meta.get("name", "")
            seq_size = len(seq_str)
            circular = inp.circular

            # File-native primers (only for sid: source)
            file_primers: list[dict] = []
            if meta.get("source") == "sid":
                seq_obj = await resolve_sequence(
                    session,
                    sid=meta["sid"],
                    load_parts=True,
                )
                if seq_obj:
                    circular = seq_obj.topology == "circular"
                    file_primers = [
                        {
                            "pid": pi.part.id,
                            "name": pi.part.names[0].name if pi.part.names else "",
                            "start": pi.start,
                            "end": pi.end,
                            "strand": pi.strand,
                            "length": pi.part.length,
                            "sequence": pi.part.sequence,
                            "source": "file",
                        }
                        for pi in seq_obj.part_instances
                        if pi.annotation_type == "primer_bind"
                    ]

            # Predicted primers from user's collection
            predicted_primers: list[dict] = []
            try:
                from hive.cloning.collections import get_active_primer_parts
                from hive.cloning.primers import find_primer_sites

                user_id = current_user_id.get()
                primer_parts = await get_active_primer_parts(session, user_id)
                if primer_parts:
                    predicted_primers = [
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
                        for pp in find_primer_sites(
                            seq_str.upper(),
                            primer_parts,
                            circular=circular,
                        )
                    ]
            except Exception as e:
                logger.warning("Primer prediction failed: %s", e)

            primers = dedup_primers(file_primers + predicted_primers)

            # Compute Tm for each primer
            for p in primers:
                pseq = p.get("sequence")
                if pseq and len(pseq) >= 5:
                    stats = analyze_primer(pseq)
                    p["tm"] = float(stats["tm"])

            return {
                "primers": primers,
                "primers_found": len(primers),
                "sequence_name": seq_name,
                "sequence_size": seq_size,
            }

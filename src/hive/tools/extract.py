"""Extract tool — get subsequence by feature, primer, or region from a sequence."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import case, select
from sqlalchemy.orm import selectinload

from hive.db import session as db
from hive.db.models import Part, PartInstance, PartName
from hive.cloning.seq import reverse_complement
from hive.tools.base import Tool
from hive.tools.resolve import resolve_sequence


class ExtractInput(BaseModel):
    sid: int | None = Field(default=None, description="Sequence ID (preferred)")
    sequence_name: str | None = Field(default=None, description="Sequence name (fallback)")
    feature_name: str | None = Field(default=None, description="Feature name to extract")
    primer_name: str | None = Field(default=None, description="Primer name to extract")
    region: str | None = Field(default=None, description="Region as start:end (1-based, inclusive)")


class ExtractTool(Tool):
    name = "extract"
    description = "Extract a subsequence by feature name, primer name, or region from a sequence."
    widget = "extract"
    tags = {"llm", "hidden", "analysis"}
    guidelines = "Extract subsequence by feature, primer, or region from a sequence."

    def __init__(self, **_):
        pass

    def input_schema(self) -> dict:
        schema = ExtractInput.model_json_schema()
        schema.pop("title", None)
        return schema

    def llm_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "sid": {"type": "integer", "description": "Sequence ID"},
                "feature_name": {"type": "string", "description": "Feature name to extract"},
                "region": {"type": "string", "description": "Region as start:end (1-based)"},
            },
            "required": ["sid"],
        }

    def format_result(self, result: dict) -> str:
        if error := result.get("error"):
            return f"Error: {error}"
        name = result.get("name", "")
        length = result.get("length", 0)
        source = result.get("source", "")
        return f"Extracted {name} from {source}: {length} bp"

    async def execute(self, params: dict[str, Any], mode: str = "direct") -> dict[str, Any]:
        inp = ExtractInput(**params)

        if inp.sid is None and not inp.sequence_name:
            return {"error": "Provide either sid or sequence_name"}

        if not db.async_session_factory:
            return {"error": "Database unavailable"}

        async with db.async_session_factory() as session:
            seq_row = await resolve_sequence(
                session, sid=inp.sid, name=inp.sequence_name,
            )

            if not seq_row:
                return {"error": f"Sequence not found: {inp.sequence_name}"}

            parent_seq = seq_row.sequence
            topology = seq_row.topology

            # Extract by primer name — query PartInstance + PartName
            if inp.primer_name:
                pi = await _find_part_instance(
                    session, seq_row.id, inp.primer_name, annotation_type="primer_bind",
                )
                if not pi:
                    return {"error": f"Primer not found: {inp.primer_name} on {seq_row.name}"}

                return {
                    "sequence": pi.part.sequence,
                    "name": pi.part.names[0].name if pi.part.names else inp.primer_name,
                    "pid": pi.part.id,
                    "source": seq_row.name,
                    "start": pi.start,
                    "end": pi.end,
                    "strand": pi.strand,
                    "length": pi.part.length,
                }

            # Extract by feature name (prefer exact match, then longest)
            if inp.feature_name:
                pi = await _find_part_instance(
                    session, seq_row.id, inp.feature_name,
                )
                if not pi:
                    return {"error": f"Feature not found: {inp.feature_name} on {seq_row.name}"}

                subseq = _slice_sequence(parent_seq, pi.start, pi.end, topology)
                if pi.strand == -1:
                    subseq = reverse_complement(subseq)

                return {
                    "sequence": subseq,
                    "name": pi.part.names[0].name if pi.part.names else inp.feature_name,
                    "pid": pi.part.id,
                    "source": seq_row.name,
                    "start": pi.start,
                    "end": pi.end,
                    "strand": pi.strand,
                    "length": len(subseq),
                }

            # Extract by region
            if inp.region:
                try:
                    parts = inp.region.split(":")
                    start = int(parts[0])
                    end = int(parts[1])
                except (ValueError, IndexError):
                    return {
                        "error": f"Invalid region format: "
                        f"{inp.region}. Use start:end (1-based)"
                    }

                # User provides 1-based inclusive -> convert to 0-based exclusive
                subseq = _slice_sequence(parent_seq, start - 1, end, topology)
                return {
                    "sequence": subseq,
                    "name": f"{start}:{end}",
                    "source": seq_row.name,
                    "start": start,
                    "end": end,
                    "strand": 1,
                    "length": len(subseq),
                }

            # No feature/primer/region — return full sequence
            return {
                "sequence": parent_seq,
                "name": seq_row.name,
                "source": seq_row.name,
                "start": 1,
                "end": len(parent_seq),
                "strand": 1,
                "length": len(parent_seq),
            }


async def _find_part_instance(
    session, seq_id: int, name: str, annotation_type: str | None = None,
) -> PartInstance | None:
    """Find a PartInstance by part name on a given sequence."""
    # Subquery: part_ids whose names match
    name_sub = (
        select(PartName.part_id)
        .where(PartName.name.ilike(f"%{name}%"))
        .subquery()
    )
    query = (
        select(PartInstance)
        .options(selectinload(PartInstance.part).selectinload(Part.names))
        .where(PartInstance.seq_id == seq_id)
        .where(PartInstance.part_id.in_(select(name_sub)))
    )
    if annotation_type:
        query = query.where(PartInstance.annotation_type == annotation_type)
    else:
        query = query.where(PartInstance.annotation_type != "primer_bind")

    # Prefer exact match, then longest
    query = query.order_by(
        case(
            (PartInstance.part_id.in_(
                select(PartName.part_id).where(PartName.name.ilike(name))
            ), 0),
            else_=1,
        ),
        (PartInstance.end - PartInstance.start).desc(),
    ).limit(1)

    return (await session.execute(query)).scalar_one_or_none()


def _slice_sequence(seq: str, start: int, end: int, topology: str) -> str:
    """Slice a sequence using 0-based, end-exclusive coordinates (sgffp convention)."""
    if start <= end:
        return seq[start:end]
    # Circular wrap-around: start > end
    if topology == "circular":
        return seq[start:] + seq[:end]
    # Linear sequence with start > end is an error
    return seq[start:end]

"""Extract tool — get subsequence by feature, primer, or region from a sequence."""

from __future__ import annotations

from typing import Any

from Bio.Seq import Seq
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from zerg.db import session as db
from zerg.db.models import Feature, IndexedFile, Primer, Sequence
from zerg.tools.base import Tool


class ExtractInput(BaseModel):
    sequence_name: str = Field(..., description="Name of the sequence/plasmid")
    feature_name: str | None = Field(default=None, description="Feature name to extract")
    primer_name: str | None = Field(default=None, description="Primer name to extract")
    region: str | None = Field(default=None, description="Region as start:end (1-based, inclusive)")


class ExtractTool(Tool):
    name = "extract"
    description = "Extract a subsequence by feature name, primer name, or region from a sequence."
    widget = "text"
    tags = {"llm", "analysis"}
    guidelines = (
        "Use to get a feature or primer subsequence before running blast, translate, "
        "digest, or gc. Put the plasmid name in `sequence_name` and the feature/primer "
        "name in `feature_name`/`primer_name`. For numeric regions use `region` as 'start:end'."
    )

    def __init__(self, **_):
        pass

    def input_schema(self) -> dict:
        schema = ExtractInput.model_json_schema()
        schema.pop("title", None)
        return schema

    def format_result(self, result: dict) -> str:
        if error := result.get("error"):
            return f"Error: {error}"
        name = result.get("name", "")
        length = result.get("length", 0)
        source = result.get("source", "")
        return f"Extracted {name} from {source}: {length} bp"

    def summary_for_llm(self, result: dict) -> str:
        if error := result.get("error"):
            return f"Error: {error}"
        seq = result.get("sequence", "")
        name = result.get("name", "")
        return f"{name}: {len(seq)} bp. Sequence: {seq}"

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        inp = ExtractInput(**params)

        if not inp.feature_name and not inp.primer_name and not inp.region:
            return {"error": "Provide feature_name, primer_name, or region"}

        if not db.async_session_factory:
            return {"error": "Database unavailable"}

        async with db.async_session_factory() as session:
            # Look up the parent sequence
            seq_row = (await session.execute(
                select(Sequence)
                .join(IndexedFile, Sequence.file_id == IndexedFile.id)
                .where(IndexedFile.status == "active")
                .where(Sequence.name.ilike(f"%{inp.sequence_name}%"))
                .limit(1)
            )).scalar_one_or_none()

            if not seq_row:
                return {"error": f"Sequence not found: {inp.sequence_name}"}

            parent_seq = seq_row.sequence
            topology = seq_row.topology

            # Extract by primer name
            if inp.primer_name:
                primer = (await session.execute(
                    select(Primer)
                    .where(Primer.seq_id == seq_row.id)
                    .where(Primer.name.ilike(f"%{inp.primer_name}%"))
                    .limit(1)
                )).scalar_one_or_none()

                if not primer:
                    return {"error": f"Primer not found: {inp.primer_name} on {seq_row.name}"}

                return {
                    "sequence": primer.sequence,
                    "name": primer.name,
                    "source": seq_row.name,
                    "start": primer.start,
                    "end": primer.end,
                    "strand": primer.strand,
                    "length": len(primer.sequence),
                }

            # Extract by feature name
            if inp.feature_name:
                feat = (await session.execute(
                    select(Feature)
                    .where(Feature.seq_id == seq_row.id)
                    .where(Feature.name.ilike(f"%{inp.feature_name}%"))
                    .limit(1)
                )).scalar_one_or_none()

                if not feat:
                    return {"error": f"Feature not found: {inp.feature_name} on {seq_row.name}"}

                subseq = _slice_sequence(parent_seq, feat.start, feat.end, topology)
                if feat.strand == -1:
                    subseq = str(Seq(subseq).reverse_complement())

                return {
                    "sequence": subseq,
                    "name": feat.name,
                    "source": seq_row.name,
                    "start": feat.start,
                    "end": feat.end,
                    "strand": feat.strand,
                    "length": len(subseq),
                }

            # Extract by region
            if inp.region:
                try:
                    parts = inp.region.split(":")
                    start = int(parts[0])
                    end = int(parts[1])
                except (ValueError, IndexError):
                    return {"error": f"Invalid region format: {inp.region}. Use start:end (1-based)"}

                subseq = _slice_sequence(parent_seq, start, end, topology)
                return {
                    "sequence": subseq,
                    "name": f"{start}:{end}",
                    "source": seq_row.name,
                    "start": start,
                    "end": end,
                    "strand": 1,
                    "length": len(subseq),
                }

        return {"error": "No extraction method specified"}


def _slice_sequence(seq: str, start: int, end: int, topology: str) -> str:
    """Slice a sequence using 1-based coordinates. Handles circular wrap-around."""
    if start <= end:
        return seq[start - 1:end]
    # Circular wrap-around: start > end
    if topology == "circular":
        return seq[start - 1:] + seq[:end]
    # Linear sequence with start > end is an error
    return seq[start - 1:end]

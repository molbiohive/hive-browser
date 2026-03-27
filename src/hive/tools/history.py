"""History tool -- cloning history tree of a sequence."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select

from hive.db import session as db
from hive.db.models import CloningStep
from hive.tools.base import Tool
from hive.tools.resolve import resolve_sequence

logger = logging.getLogger(__name__)


class HistoryInput(BaseModel):
    sid: int | None = Field(default=None, description="Sequence ID (preferred)")
    name: str | None = Field(default=None, description="Sequence name (fallback)")


class HistoryTool(Tool):
    name = "history"
    description = ("cloning history", "Show the cloning history of a sequence -- assembly steps, primers, enzymes used.")
    tags = {"info"}

    def __init__(self, **_):
        pass

    def input_schema(self) -> dict:
        schema = HistoryInput.model_json_schema()
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
        name = result.get("sequence_name", "?")
        steps = result.get("steps", 0)
        return f"{name} -- {steps} cloning step(s)"

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        inp = HistoryInput(**params)

        if inp.sid is None and not inp.name:
            return {"error": "Provide either sid or name"}

        if not db.async_session_factory:
            return {"error": "Database unavailable"}

        async with db.async_session_factory() as session:
            seq = await resolve_sequence(
                session,
                sid=inp.sid,
                name=inp.name,
                load_file=True,
                load_parts=True,
            )
            if not seq:
                return {"error": f"Sequence not found: {inp.sid or inp.name}"}

            # Load cloning steps
            result = await session.execute(
                select(CloningStep)
                .where(CloningStep.sequence_id == seq.id)
                .order_by(CloningStep.node_id)
            )
            steps = list(result.scalars().all())

            if not steps:
                return {"error": f"No cloning history for {seq.name}"}

            # Build tree: reconstruct parent-child from parent_step_id
            children_map: dict[int, list[CloningStep]] = {}
            root_step = None

            for s in steps:
                if s.parent_step_id is None:
                    root_step = s
                else:
                    # Find parent's node_id
                    for ps in steps:
                        if ps.id == s.parent_step_id:
                            children_map.setdefault(ps.node_id, []).append(s)
                            break

            if not root_step:
                root_step = steps[0]

            # Map to CloningNode format for hatchlings CloningHistoryViewer
            root_node = _to_cloning_node(root_step, children_map)

            # Override root node parts with actual PartInstance data from DB
            if seq.part_instances:
                root_node["parts"] = [
                    {
                        "pid": pi.part.id,
                        "name": pi.part.names[0].name if pi.part.names else "",
                        "type": pi.annotation_type,
                        "start": pi.start,
                        "end": pi.end,
                        "strand": pi.strand or 1,
                    }
                    for pi in seq.part_instances
                    if pi.annotation_type != "primer_bind"
                ]

            return {
                "root": root_node,
                "sequence_name": seq.name,
                "sequence_size": seq.length,
                "steps": len(steps),
            }


def _to_cloning_node(step: CloningStep, children_map: dict[int, list]) -> dict:
    """Convert a CloningStep to hatchlings CloningNode format (recursive).

    Includes full features, primers, and oligos per node for the viewer.
    """
    node: dict[str, Any] = {
        "id": str(step.node_id),
        "name": step.name,
        "size": step.seq_len,
        "topology": "circular" if step.circular else "linear",
    }

    # Map features to hatchlings Part[] format (CloningNode expects "parts", not "features")
    if step.features:
        node["parts"] = [
            {
                "name": f.get("name", ""),
                "type": f.get("type", "misc_feature"),
                "start": f.get("start", 0),
                "end": f.get("end", 0),
                "strand": f.get("strand", 1) or 1,
            }
            for f in step.features
        ]

    kids = children_map.get(step.node_id, [])
    if kids:
        enzymes = [e["name"] for e in (step.enzymes or [])]
        oligo_primers = [o["name"] for o in (step.oligos or [])]
        action: dict[str, Any] = {"type": step.operation}
        if enzymes:
            action["enzymes"] = enzymes
        if oligo_primers:
            action["primers"] = oligo_primers

        node["source"] = {
            "action": action,
            "inputs": [{"node": _to_cloning_node(child, children_map)} for child in kids],
        }

    return node

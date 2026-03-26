"""Parts tool -- unified part lookup by PID or SID."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from hive.config import display_file_path
from hive.db import session as db
from hive.db.models import Annotation, Part, PartInstance, PartName
from hive.tools.base import Tool
from hive.tools.resolve import resolve_part, resolve_sequence

logger = logging.getLogger(__name__)


class PartsInput(BaseModel):
    pid: int | None = Field(default=None, description="Part ID for canonical lookup")
    sid: int | None = Field(default=None, description="Sequence ID to list parts on")
    type: str | None = Field(
        default=None,
        description="Filter by annotation type (e.g. CDS, promoter, primer_bind)",
    )
    find_relatives: bool = Field(
        default=False,
        description="BLAST for similar parts (PID mode only)",
    )


class PartsTool(Tool):
    name = "parts"
    description = "Look up a part by PID, or list all parts on a sequence by SID."
    tags = {"info"}
    guidelines = (
        "Look up a part by PID (canonical data: names, instances across sequences, "
        "annotations, libraries, sequence) or list all parts on a sequence by SID "
        "(with optional type filter like CDS, promoter, primer_bind)."
    )

    def __init__(self, config=None, **_):
        self._config = config

    def input_schema(self) -> dict:
        schema = PartsInput.model_json_schema()
        schema.pop("title", None)
        return schema

    def llm_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "pid": {"type": "integer", "description": "Part ID"},
                "sid": {"type": "integer", "description": "Sequence ID"},
                "type": {"type": "string", "description": "Filter: CDS, promoter, primer_bind"},
            },
        }

    def format_result(self, result: dict) -> str:
        if error := result.get("error"):
            return f"Error: {error}"
        if "part" in result:
            p = result["part"]
            names = ", ".join(p.get("names", [])) or "unnamed"
            return (
                f"Part PID {p['pid']} ({names}): {p['length']} bp,"
                f" {result['instances_count']} instance(s)"
            )
        total = result.get("total", 0)
        seq_name = result.get("sequence_name", "")
        return f"{total} part(s) on {seq_name}"

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        inp = PartsInput(**{k: v for k, v in params.items() if v is not None})

        if inp.pid is not None:
            return await self._pid_mode(inp)
        elif inp.sid is not None:
            return await self._sid_mode(inp)
        else:
            return {"error": "Provide either pid or sid"}

    async def _pid_mode(self, inp: PartsInput) -> dict[str, Any]:
        """Canonical part lookup by PID."""
        if not db.async_session_factory:
            return {"error": "Database unavailable"}

        async with db.async_session_factory() as session:
            part = await resolve_part(
                session,
                pid=inp.pid,
                load_names=True,
                load_instances=True,
                load_annotations=True,
                load_libraries=True,
            )
            if not part:
                return {"error": f"Part not found: PID {inp.pid}"}

            instances = [
                {
                    "sid": pi.sequence.id,
                    "sequence_name": pi.sequence.name,
                    "annotation_type": pi.annotation_type,
                    "start": pi.start,
                    "end": pi.end,
                    "strand": pi.strand,
                    "file_path": display_file_path(pi.sequence.file.file_path),
                }
                for pi in part.instances
                if pi.sequence and pi.sequence.file
            ]

            annotations = [
                {"key": a.key, "value": a.value, "source": a.source} for a in part.annotations
            ]

            libraries = [
                {"id": lm.library.id, "name": lm.library.name}
                for lm in part.library_members
                if lm.library
            ]

            # Resolve variant annotations into enriched records
            variants = await _resolve_variants(session, part.annotations)

            result: dict[str, Any] = {
                "part": {
                    "pid": part.id,
                    "names": [n.name for n in part.names],
                    "molecule": part.molecule,
                    "length": part.length,
                    "sequence": part.sequence,
                    "sequence_hash": part.sequence_hash,
                },
                "instances": instances,
                "instances_count": len(instances),
                "annotations": annotations,
                "libraries": libraries,
            }

            if variants:
                result["variants"] = variants

            if inp.find_relatives and self._config:
                relatives = await self._find_relatives(part)
                result["relatives"] = relatives

            return result

    async def _sid_mode(self, inp: PartsInput) -> dict[str, Any]:
        """List all parts on a sequence."""
        if not db.async_session_factory:
            return {"error": "Database unavailable"}

        async with db.async_session_factory() as session:
            seq = await resolve_sequence(session, sid=inp.sid)
            if not seq:
                return {"error": f"Sequence not found: SID {inp.sid}"}

            query = (
                select(PartInstance)
                .join(Part, PartInstance.part_id == Part.id)
                .options(selectinload(PartInstance.part).selectinload(Part.names))
                .where(PartInstance.seq_id == seq.id)
            )
            if inp.type:
                query = query.where(PartInstance.annotation_type.ilike(inp.type))
            query = query.order_by(PartInstance.start)

            rows = (await session.execute(query)).scalars().all()

            parts = [
                {
                    "pid": pi.part.id,
                    "name": pi.part.names[0].name if pi.part.names else "",
                    "type": pi.annotation_type,
                    "start": pi.start,
                    "end": pi.end,
                    "strand": pi.strand,
                    "length": pi.part.length,
                }
                for pi in rows
            ]

            return {
                "parts": parts,
                "total": len(parts),
                "sequence_name": seq.name,
            }

    async def _find_relatives(self, part: Part) -> list[dict]:
        """BLAST the part's sequence and return top 10 hits."""
        try:
            from hive.tools.blast import BlastTool

            blast = BlastTool(config=self._config)
            result = await blast.execute(
                {"sequence": part.sequence, "max_hits": 10},
            )
            return result.get("hits", [])
        except Exception as e:
            logger.warning("find_relatives BLAST failed: %s", e)
            return []


async def _resolve_variants(session, annotations: list) -> list[dict]:
    """Resolve variant_of and blast_similar annotations into enriched records."""
    import json

    variant_pids: dict[int, dict] = {}

    for a in annotations:
        if a.key not in ("variant_of", "blast_similar"):
            continue
        d = json.loads(a.value)
        if a.key == "variant_of":
            for pid in d.get("pids", []):
                variant_pids.setdefault(pid, {"source": "name_collision"})
        else:
            pid = d.get("pid")
            if pid is not None:
                variant_pids.setdefault(pid, {})
                variant_pids[pid]["source"] = "blast"
                if "identity" in d:
                    variant_pids[pid]["identity"] = round(float(d["identity"]), 1)
                if "coverage" in d:
                    variant_pids[pid]["coverage"] = round(float(d["coverage"]), 1)

    if not variant_pids:
        return []

    pids = list(variant_pids.keys())
    stmt = (
        select(Part)
        .where(Part.id.in_(pids))
        .options(
            selectinload(Part.names),
            selectinload(Part.instances),
        )
    )
    rows = (await session.execute(stmt)).scalars().all()
    part_map = {p.id: p for p in rows}

    result = []
    for pid in pids:
        part = part_map.get(pid)
        if not part:
            continue
        types = list({pi.annotation_type for pi in part.instances if pi.annotation_type})
        entry: dict[str, Any] = {
            "pid": part.id,
            "names": [n.name for n in part.names],
            "length": part.length,
            "types": types,
            "source": variant_pids[pid].get("source", "unknown"),
        }
        if "identity" in variant_pids[pid]:
            entry["identity"] = variant_pids[pid]["identity"]
        if "coverage" in variant_pids[pid]:
            entry["coverage"] = variant_pids[pid]["coverage"]
        result.append(entry)

    return result

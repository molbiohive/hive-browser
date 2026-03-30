"""Profile tool -- full details of a single sequence."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from hive.config import display_file_path
from hive.context import current_user_id
from hive.db import session as db
from hive.libs.classify import analyze_primer
from hive.tools.base import Tool
from hive.tools.resolve import dedup_primers, resolve_sequence

logger = logging.getLogger(__name__)


class ProfileInput(BaseModel):
    sid: int | None = Field(default=None, description="Sequence ID (preferred)")
    name: str | None = Field(default=None, description="Sequence name (fallback)")


class ProfileTool(Tool):
    name = "profile"
    description = (
        "sequence detail",
        "Full details and visual inspection of a specific sequence: "
        "plasmid map, annotated viewer, metadata, features, primers, cut sites.",
    )
    tags = {"info"}
    advanced = {"name"}

    def __init__(self, **_):
        pass

    def input_schema(self) -> dict:
        schema = ProfileInput.model_json_schema()
        schema.pop("title", None)
        return schema

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
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
                    "sequence": pi.part.sequence,
                    "molecule": pi.part.molecule,
                    "qualifiers": pi.qualifiers,
                }
                for pi in seq.part_instances
            ]

            circular = seq.topology == "circular"

            # Scan for restriction cut sites (optionally filtered by collection)
            cut_sites: list[dict] = []
            if seq.sequence and seq.molecule in (None, "DNA", "dna"):
                try:
                    from hive.context.collections import get_active_enzyme_names
                    from hive.libs.enzymes import load_enzymes
                    from hive.molbio.enzymes import find_all_cutters, find_cut_sites

                    enzymes = await load_enzymes(session)
                    user_id = current_user_id.get()
                    active_names = await get_active_enzyme_names(session, user_id)

                    if active_names:
                        result = find_cut_sites(
                            seq.sequence.upper(),
                            active_names,
                            enzymes,
                            circular=circular,
                        )
                        for er in result["enzyme_results"]:
                            enz = enzymes.get(er["name"].upper())
                            if not enz:
                                continue
                            for pos in er["sites"]:
                                cut_sites.append(
                                    {
                                        "enzyme": er["name"],
                                        "position": pos,
                                        "end": pos + enz.length,
                                        "strand": 1,
                                        "cutPosition": enz.cut5,
                                        "complementCutPosition": enz.cut3,
                                        "overhang": (
                                            "5'"
                                            if enz.overhang < 0
                                            else ("3'" if enz.overhang > 0 else "blunt")
                                        ),
                                    }
                                )
                    else:
                        cutters = find_all_cutters(
                            seq.sequence.upper(),
                            enzymes,
                            circular=circular,
                        )
                        for c in cutters:
                            enz = enzymes.get(c["name"].upper())
                            if not enz:
                                continue
                            for pos in c["positions"]:
                                cut_sites.append(
                                    {
                                        "enzyme": c["name"],
                                        "position": pos,
                                        "end": pos + enz.length,
                                        "strand": 1,
                                        "cutPosition": enz.cut5,
                                        "complementCutPosition": enz.cut3,
                                        "overhang": (
                                            "5'"
                                            if enz.overhang < 0
                                            else ("3'" if enz.overhang > 0 else "blunt")
                                        ),
                                    }
                                )
                except Exception as e:
                    logger.warning("Cut site scan failed: %s", e)

            # Predict primer binding from collection
            predicted_primers: list[dict] = []
            if seq.sequence and seq.molecule in (None, "DNA", "dna"):
                try:
                    from hive.context.collections import get_active_primer_parts
                    from hive.molbio.primers import find_primer_sites

                    user_id = current_user_id.get()
                    primer_parts = await get_active_primer_parts(session, user_id)
                    if primer_parts:
                        predicted_primers = find_primer_sites(
                            seq.sequence.upper(),
                            primer_parts,
                            circular=circular,
                        )
                except Exception as e:
                    logger.warning("Primer prediction failed: %s", e)

            primers = dedup_primers(
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
                ]
                + [
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
            )

            # Compute Tm for each primer with a sequence
            for p in primers:
                pseq = p.get("sequence")
                if pseq and len(pseq) >= 5:
                    stats = analyze_primer(pseq)
                    p["tm"] = float(stats["tm"])

            # Build translations from features with translated segments
            translations = []
            for p in parts_list:
                quals = p.get("qualifiers") or {}
                aa = quals.get("translation")
                if not quals.get("translated") or not aa:
                    continue
                # Multi-segment CDS: comma-separated AAs -> concatenate
                if "," in aa:
                    aa = aa.replace(",", "")
                # Frame from codon_start (1-based) or reading_frame
                cs = quals.get("codon_start")
                rf = quals.get("reading_frame")
                if cs is not None:
                    frame = int(cs) - 1
                elif rf is not None:
                    frame = abs(int(rf)) - 1
                else:
                    frame = 0
                translations.append(
                    {
                        "start": p["start"],
                        "end": p["end"],
                        "strand": p["strand"],
                        "aminoAcids": aa,
                        "frame": max(0, min(2, frame)),
                    }
                )

            return {
                "sequence": {
                    "sid": seq.id,
                    "name": seq.name,
                    "size_bp": seq.length,
                    "topology": seq.topology,
                    "molecule": seq.molecule,
                    "description": seq.description,
                    "has_history": seq.has_history,
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
                "translations": translations,
                "primers": primers,
                "cut_sites": cut_sites,
                "file": {
                    "path": display_file_path(seq.file.file_path),
                    "format": seq.file.format,
                    "size": seq.file.file_size,
                    "indexed_at": seq.file.indexed_at.isoformat() if seq.file.indexed_at else None,
                },
            }

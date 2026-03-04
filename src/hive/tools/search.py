"""Search tool — fuzzy metadata + part name search using pg_trgm.

Supports boolean queries: "KanR && circular" (AND), "GFP || RFP" (OR).
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import Text, and_, cast, desc, func, or_, select
from sqlalchemy.orm import selectinload

from hive.config import display_file_path
from hive.db import session as db
from hive.db.models import IndexedFile, Part, PartInstance, PartName, Sequence
from hive.tools.base import Tool


def _parse_bool_query(query: str) -> tuple[list[str], str]:
    """Parse boolean operators in query string.

    Returns (terms, operator) where operator is 'and', 'or', or 'single'.
    """
    if "&&" in query:
        terms = [t.strip() for t in re.split(r"\s*&&\s*", query) if t.strip()]
        return (terms, "and") if len(terms) > 1 else (terms, "single")
    if "||" in query:
        terms = [t.strip() for t in re.split(r"\s*\|\|\s*", query) if t.strip()]
        return (terms, "or") if len(terms) > 1 else (terms, "single")
    return [query.strip()], "single"


class SearchInput(BaseModel):
    query: str = Field(
        ...,
        description="Keyword (name, feature, or description). Use && for AND, || for OR.",
    )
    tags: str | None = Field(
        default=None,
        description="Directory or project context (e.g. folder name, project name)",
    )
    filters: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional: topology, size_min, size_max",
    )


class SearchResultItem(BaseModel):
    sid: int
    name: str
    size_bp: int
    topology: str
    features: list[str]
    tags: list[str] = []
    file_path: str
    score: float


class SearchTool(Tool):
    name = "search"
    description = "Search sequences by name, features, tags (directory context), and metadata."
    widget = "table"
    tags = {"llm", "search"}
    guidelines = (
        "Fuzzy keyword search across sequences AND parts. Returns both matching "
        "sequences (with SIDs) and matching parts (with PIDs and instance counts). "
        "IMPORTANT: When user says 'X and Y' or 'X with Y' or 'X that have Y', "
        "ALWAYS use && in query: 'X && Y'. Without && terms are single-term fuzzy. "
        "If the user mentions a project, folder, or directory context, "
        "put it in the tags parameter. "
        "Use PIDs from the parts section for follow-up tools (align, blast, extract)."
    )

    def __init__(self, **_):
        pass

    def input_schema(self) -> dict:
        schema = SearchInput.model_json_schema()
        schema.pop("title", None)
        return schema

    def llm_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keyword. Use && for AND, || for OR."},
                "tags": {"type": "string", "description": "Directory/project context"},
            },
            "required": ["query"],
        }

    def format_result(self, result: dict) -> str:
        if error := result.get("error"):
            return f"Error: {error}"
        total = result.get("total", 0)
        parts_total = result.get("parts_total", 0)
        query = result.get("query", "")
        parts_msg = f", {parts_total} part(s)" if parts_total else ""
        if total or parts_total:
            return f"Found {total} sequence(s){parts_msg} for '{query}'."
        return f"No results for '{query}'."


    async def execute(self, params: dict[str, Any], mode: str = "direct") -> dict[str, Any]:
        """Execute search with pg_trgm similarity + filters.

        Supports boolean queries: "KanR && circular" (AND), "GFP || RFP" (OR).
        """
        inp = SearchInput(**params)

        if not db.async_session_factory:
            return {"results": [], "total": 0, "query": inp.query, "error": "Database unavailable"}

        terms, op = _parse_bool_query(inp.query)

        async with db.async_session_factory() as session:
            # Per-term: similarity expressions, part name subqueries, match conditions
            term_scores = []
            term_conditions = []
            pn_subs = []

            for i, term in enumerate(terms):
                seq_sim = func.similarity(Sequence.name, term)
                desc_sim = func.coalesce(func.similarity(Sequence.description, term), 0)
                tags_sim = func.coalesce(
                    func.similarity(cast(Sequence.meta["tags"], Text), term), 0
                )

                # Part name similarity subquery (replaces Feature name subquery)
                pn_sub = (
                    select(
                        PartInstance.seq_id,
                        func.max(func.similarity(PartName.name, term)).label(f"ps_{i}"),
                    )
                    .join(PartName, PartInstance.part_id == PartName.part_id)
                    .group_by(PartInstance.seq_id)
                    .subquery(name=f"pn_{i}")
                )
                part_score = func.coalesce(getattr(pn_sub.c, f"ps_{i}"), 0)

                # Exact match on topology (circular/linear)
                topo_match = func.lower(Sequence.topology) == func.lower(term)

                score = func.greatest(seq_sim, desc_sim, part_score, tags_sim)
                condition = or_(
                    seq_sim > 0.1, desc_sim > 0.1, part_score > 0.1,
                    tags_sim > 0.1, topo_match,
                )

                term_scores.append(score)
                term_conditions.append(condition)
                pn_subs.append(pn_sub)

            # Ordering: worst term for AND (all must be good), best for OR
            if len(term_scores) == 1:
                combined = term_scores[0]
            elif op == "and":
                combined = func.least(*term_scores)
            else:
                combined = func.greatest(*term_scores)

            # Base query
            stmt = (
                select(Sequence, combined.label("score"), IndexedFile.file_path)
                .join(IndexedFile, Sequence.file_id == IndexedFile.id)
                .options(
                    selectinload(Sequence.part_instances)
                    .selectinload(PartInstance.part)
                    .selectinload(Part.names)
                )
                .where(IndexedFile.status == "active")
            )

            # Join part name subqueries
            for pn_sub in pn_subs:
                stmt = stmt.outerjoin(pn_sub, Sequence.id == pn_sub.c.seq_id)

            # Boolean condition
            if op == "and":
                stmt = stmt.where(and_(*term_conditions))
            elif op == "or":
                stmt = stmt.where(or_(*term_conditions))
            else:
                stmt = stmt.where(term_conditions[0])

            stmt = stmt.order_by(combined.desc())

            # Tags filter (directory/project context from LLM)
            if inp.tags:
                stmt = stmt.where(
                    func.similarity(cast(Sequence.meta["tags"], Text), inp.tags) > 0.1
                )

            # Apply filters
            if topo := inp.filters.get("topology"):
                stmt = stmt.where(Sequence.topology == topo)
            if size_min := inp.filters.get("size_min"):
                stmt = stmt.where(Sequence.length >= int(size_min))
            if size_max := inp.filters.get("size_max"):
                stmt = stmt.where(Sequence.length <= int(size_max))

            rows = (await session.execute(stmt)).all()

            results = []
            for seq, score, file_path in rows:
                # Collect part names (first name per part) as "features" for display
                part_names = []
                for pi in seq.part_instances:
                    if pi.part and pi.part.names:
                        part_names.append(pi.part.names[0].name)
                meta = seq.meta or {}
                results.append(
                    SearchResultItem(
                        sid=seq.id,
                        name=seq.name,
                        size_bp=seq.length,
                        topology=seq.topology,
                        features=part_names,
                        tags=meta.get("tags", []),
                        file_path=display_file_path(file_path),
                        score=round(float(score), 3),
                    ).model_dump()
                )

            # --- Part-level search ---
            parts = await _search_parts(session, terms, op)

        return {
            "results": results,
            "total": len(results),
            "parts": parts,
            "parts_total": len(parts),
            "query": inp.query,
        }


async def _search_parts(
    session: Any, terms: list[str], op: str,
) -> list[dict]:
    """Search parts by name and annotation type similarity."""
    term_scores = []
    term_conditions = []

    for term in terms:
        name_score = func.max(func.similarity(PartName.name, term))
        type_score = func.max(func.coalesce(
            func.similarity(PartInstance.annotation_type, term), 0,
        ))
        score_expr = func.greatest(name_score, type_score)
        term_scores.append(score_expr)
        term_conditions.append(score_expr > 0.15)

    # Build combined score expression
    if len(term_scores) == 1:
        combined = term_scores[0]
    elif op == "and":
        combined = func.least(*term_scores)
    else:
        combined = func.greatest(*term_scores)

    # Group by Part, get best match score across name + type
    stmt = (
        select(Part.id, combined.label("score"))
        .join(PartName, Part.id == PartName.part_id)
        .join(PartInstance, Part.id == PartInstance.part_id)
        .group_by(Part.id)
    )

    # Apply boolean conditions
    if op == "and":
        for cond in term_conditions:
            stmt = stmt.having(cond)
    elif op == "or":
        stmt = stmt.having(or_(*term_conditions))
    else:
        stmt = stmt.having(term_conditions[0])

    stmt = stmt.order_by(desc("score")).limit(20)
    rows = (await session.execute(stmt)).all()

    if not rows:
        return []

    # Load full Part objects with names and instances
    part_ids = [r[0] for r in rows]
    score_map = {r[0]: round(float(r[1]), 2) for r in rows}

    parts_stmt = (
        select(Part)
        .where(Part.id.in_(part_ids))
        .options(
            selectinload(Part.names),
            selectinload(Part.instances),
        )
    )
    parts = (await session.execute(parts_stmt)).scalars().all()

    # Build result dicts preserving score order
    part_map = {p.id: p for p in parts}
    result = []
    for pid in part_ids:
        part = part_map.get(pid)
        if not part:
            continue
        types = list({pi.annotation_type for pi in part.instances if pi.annotation_type})
        result.append({
            "pid": part.id,
            "names": [n.name for n in part.names],
            "molecule": part.molecule,
            "length": part.length,
            "instance_count": len(part.instances),
            "types": types,
            "score": score_map[pid],
        })

    return result

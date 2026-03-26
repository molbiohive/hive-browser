"""Search tool — BM25 full-text search using ParadeDB pg_search.

Supports boolean queries: "KanR && circular" (AND), "GFP || RFP" (OR).
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import Text, bindparam, cast, desc, func, select, text
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


def _bm25_query(terms: list[str], op: str) -> str:
    """Build a ParadeDB query string from parsed terms and operator.

    Each term is quoted to handle multi-word and hyphenated names.
    """
    escaped = [f'"{t}"' for t in terms]
    if op == "and":
        return " AND ".join(escaped)
    return " OR ".join(escaped)


class SearchInput(BaseModel):
    query: str = Field(
        ...,
        description="Keyword (name, feature, or description). Use && for AND, || for OR. Use * to list all.",
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
    tags = {"search"}
    guidelines = (
        "BM25 keyword search across sequences AND parts. Returns both matching "
        "sequences (with SIDs) and matching parts (with PIDs and instance counts). "
        "IMPORTANT: When user says 'X and Y' or 'X with Y' or 'X that have Y', "
        "ALWAYS use && in query: 'X && Y'. Without && terms are single-term search. "
        "Use query='*' to list ALL sequences (useful for 'show everything', 'list all'). "
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
                "query": {
                    "type": "string",
                    "description": "Keyword. Use && for AND, || for OR. Use * to list all.",
                },
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

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        """Execute search with ParadeDB BM25 full-text search.

        Supports boolean queries: "KanR && circular" (AND), "GFP || RFP" (OR).
        """
        inp = SearchInput(**params)

        if not db.async_session_factory:
            return {"results": [], "total": 0, "query": inp.query, "error": "Database unavailable"}

        # Wildcard: list all sequences (respects filters/tags)
        if inp.query.strip() == "*":
            return await self._execute_all(inp)

        terms, op = _parse_bool_query(inp.query)
        bm25_q = _bm25_query(terms, op)

        # Choose BM25 operator: &&& (conjunction) for AND, ||| (disjunction) for OR/single
        bm25_op = "&&&" if op == "and" else "|||"

        async with db.async_session_factory() as session:
            # BM25 search on sequences via search_text + name
            score_expr = text("pdb.score(sequences.id)")

            stmt = (
                select(Sequence, score_expr.label("score"), IndexedFile.file_path)
                .join(IndexedFile, Sequence.file_id == IndexedFile.id)
                .options(
                    selectinload(Sequence.part_instances)
                    .selectinload(PartInstance.part)
                    .selectinload(Part.names)
                )
                .where(IndexedFile.status == "active")
                .where(
                    text(
                        f"(sequences.search_text {bm25_op} :bm25_q"
                        f" OR sequences.name {bm25_op} :bm25_q)"
                    ).bindparams(bindparam("bm25_q", value=bm25_q))
                )
                .order_by(score_expr.desc())
            )

            # Tags filter
            if inp.tags:
                stmt = stmt.where(cast(Sequence.meta["tags"], Text).contains(inp.tags))

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
            parts = await _search_parts(session, bm25_q)

        return {
            "results": results,
            "total": len(results),
            "parts": parts,
            "parts_total": len(parts),
            "query": inp.query,
        }

    async def _execute_all(self, inp: SearchInput) -> dict[str, Any]:
        """Return all sequences, ordered by name. Filters and tags still apply."""
        async with db.async_session_factory() as session:
            stmt = (
                select(Sequence, IndexedFile.file_path)
                .join(IndexedFile, Sequence.file_id == IndexedFile.id)
                .options(
                    selectinload(Sequence.part_instances)
                    .selectinload(PartInstance.part)
                    .selectinload(Part.names)
                )
                .where(IndexedFile.status == "active")
                .order_by(Sequence.name)
            )

            if inp.tags:
                stmt = stmt.where(cast(Sequence.meta["tags"], Text).contains(inp.tags))
            if topo := inp.filters.get("topology"):
                stmt = stmt.where(Sequence.topology == topo)
            if size_min := inp.filters.get("size_min"):
                stmt = stmt.where(Sequence.length >= int(size_min))
            if size_max := inp.filters.get("size_max"):
                stmt = stmt.where(Sequence.length <= int(size_max))

            rows = (await session.execute(stmt)).all()

            results = []
            for seq, file_path in rows:
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
                        score=1.0,
                    ).model_dump()
                )

        return {
            "results": results,
            "total": len(results),
            "parts": [],
            "parts_total": 0,
            "query": inp.query,
        }


async def _search_parts(session: Any, bm25_q: str) -> list[dict]:
    """Search parts by name using ParadeDB BM25 on part_names."""
    score_expr = text("pdb.score(part_names.id)")

    # BM25 search on part_names (disjunction -- any term matches)
    pn_stmt = (
        select(
            PartName.part_id,
            func.max(score_expr).label("score"),
        )
        .where(text("part_names.name ||| :bm25_q").bindparams(bindparam("bm25_q", value=bm25_q)))
        .group_by(PartName.part_id)
        .order_by(desc("score"))
    )
    rows = (await session.execute(pn_stmt)).all()

    if not rows:
        return []

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
        result.append(
            {
                "pid": part.id,
                "names": [n.name for n in part.names],
                "molecule": part.molecule,
                "length": part.length,
                "instance_count": len(part.instances),
                "types": types,
                "score": score_map[pid],
            }
        )

    return result

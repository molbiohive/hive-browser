"""Search tool — fuzzy metadata + feature search using pg_trgm.

Supports boolean queries: "KanR && circular" (AND), "GFP || RFP" (OR).
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import Text, and_, cast, func, or_, select
from sqlalchemy.orm import selectinload

from hive.config import display_file_path
from hive.db import session as db
from hive.db.models import Feature, IndexedFile, Sequence
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
        description="Optional: topology, size_min, size_max, feature_type",
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
        "Fuzzy keyword search across name, features, description, and directory tags. "
        "IMPORTANT: When user says 'X and Y' or 'X with Y' or 'X that have Y', "
        "ALWAYS use && in query: 'X && Y'. Without && terms are single-term fuzzy. "
        "If the user mentions a project, folder, or directory context, "
        "put it in the tags parameter."
    )

    def __init__(self, **_):
        pass

    def input_schema(self) -> dict:
        schema = SearchInput.model_json_schema()
        schema.pop("title", None)
        return schema

    def format_result(self, result: dict) -> str:
        if error := result.get("error"):
            return f"Error: {error}"
        total = result.get("total", 0)
        query = result.get("query", "")
        return f"Found {total} result(s) for '{query}'." if total else f"No results for '{query}'."

    async def execute(self, params: dict[str, Any], mode: str = "direct") -> dict[str, Any]:
        """Execute search with pg_trgm similarity + filters.

        Supports boolean queries: "KanR && circular" (AND), "GFP || RFP" (OR).
        """
        inp = SearchInput(**params)

        if not db.async_session_factory:
            return {"results": [], "total": 0, "query": inp.query, "error": "Database unavailable"}

        terms, op = _parse_bool_query(inp.query)

        async with db.async_session_factory() as session:
            # Per-term: similarity expressions, feature subqueries, match conditions
            term_scores = []
            term_conditions = []
            feat_subs = []

            for i, term in enumerate(terms):
                seq_sim = func.similarity(Sequence.name, term)
                desc_sim = func.coalesce(func.similarity(Sequence.description, term), 0)
                tags_sim = func.coalesce(
                    func.similarity(cast(Sequence.meta["tags"], Text), term), 0
                )

                fsub = (
                    select(
                        Feature.seq_id,
                        func.max(func.similarity(Feature.name, term)).label(f"fs_{i}"),
                    )
                    .group_by(Feature.seq_id)
                    .subquery(name=f"feat_{i}")
                )
                feat_score = func.coalesce(getattr(fsub.c, f"fs_{i}"), 0)

                # Exact match on topology (circular/linear)
                topo_match = func.lower(Sequence.topology) == func.lower(term)

                score = func.greatest(seq_sim, desc_sim, feat_score, tags_sim)
                condition = or_(
                    seq_sim > 0.1, desc_sim > 0.1, feat_score > 0.1,
                    tags_sim > 0.1, topo_match,
                )

                term_scores.append(score)
                term_conditions.append(condition)
                feat_subs.append(fsub)

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
                .options(selectinload(Sequence.features))
                .where(IndexedFile.status == "active")
            )

            # Join feature subqueries
            for fsub in feat_subs:
                stmt = stmt.outerjoin(fsub, Sequence.id == fsub.c.seq_id)

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
                stmt = stmt.where(Sequence.size_bp >= int(size_min))
            if size_max := inp.filters.get("size_max"):
                stmt = stmt.where(Sequence.size_bp <= int(size_max))
            if feat_type := inp.filters.get("feature_type"):
                if isinstance(feat_type, list):
                    feat_type = feat_type[0] if feat_type else None
                if feat_type:
                    stmt = stmt.where(
                        Sequence.id.in_(
                            select(Feature.seq_id).where(Feature.type == feat_type)
                        )
                    )

            rows = (await session.execute(stmt)).all()

            results = []
            for seq, score, file_path in rows:
                feat_names = [f.name for f in seq.features]
                meta = seq.meta or {}
                results.append(
                    SearchResultItem(
                        sid=seq.id,
                        name=seq.name,
                        size_bp=seq.size_bp,
                        topology=seq.topology,
                        features=feat_names,
                        tags=meta.get("tags", []),
                        file_path=display_file_path(file_path),
                        score=round(float(score), 3),
                    ).model_dump()
                )

        return {
            "results": results,
            "total": len(results),
            "query": inp.query,
        }

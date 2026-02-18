"""Search tool — fuzzy metadata + feature search using pg_trgm."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import selectinload

from zerg.db import session as db
from zerg.db.models import Feature, IndexedFile, Sequence
from zerg.tools.base import Tool


class SearchInput(BaseModel):
    query: str = Field(..., description="Search text — matches against sequence names, feature names, and descriptions. Use the main search term here, e.g. 'GFP' or 'ampicillin'.")
    filters: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional filters to narrow results. Keys: topology ('circular'|'linear'), size_min (int), size_max (int), feature_type (GenBank type like 'CDS', 'promoter', 'rep_origin' — NOT biological concepts like 'plasmid'). Only use filters when the user explicitly requests them.",
    )
    limit: int = Field(default=20, ge=1, le=100)


class SearchResultItem(BaseModel):
    id: int
    name: str
    size_bp: int
    topology: str
    features: list[str]
    file_path: str
    score: float


class SearchTool(Tool):
    name = "search"
    description = (
        "Search sequences by name, features, resistance markers, and metadata. "
        "Supports fuzzy matching."
    )
    widget = "table"
    tags = {"llm", "search"}
    guidelines = (
        "Put the main keyword in `query` (e.g. 'GFP', 'ampicillin', 'pUC19'). "
        "Leave `filters` empty unless the user explicitly asks to filter by topology or size. "
        "Do NOT add `feature_type` unless the user specifically requests it. "
        "NEVER put nucleotide sequences in `query` — use blast for sequence similarity."
    )

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

    def summary_for_llm(self, result: dict) -> str:
        total = result.get("total", 0)
        query = result.get("query", "")
        if not total:
            return f"No results for '{query}'."
        names = [r["name"] for r in result.get("results", [])[:5]]
        return f"Found {total} result(s) for '{query}'. Top matches: {', '.join(names)}."

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        """Execute search with pg_trgm similarity + filters."""
        inp = SearchInput(**params)

        if not db.async_session_factory:
            return {"results": [], "total": 0, "query": inp.query, "error": "Database unavailable"}

        async with db.async_session_factory() as session:
            # Build trigram similarity score expressions
            seq_sim = func.similarity(Sequence.name, inp.query)
            desc_sim = func.coalesce(func.similarity(Sequence.description, inp.query), 0)

            # Subquery: best feature match score per sequence
            feat_sub = (
                select(
                    Feature.seq_id,
                    func.max(func.similarity(Feature.name, inp.query)).label("feat_score"),
                )
                .group_by(Feature.seq_id)
                .subquery()
            )

            # Combined score: max of (name_sim, desc_sim, feat_sim)
            feat_score = func.coalesce(feat_sub.c.feat_score, 0)
            combined = func.greatest(seq_sim, desc_sim, feat_score)

            # Base query
            stmt = (
                select(
                    Sequence,
                    combined.label("score"),
                    IndexedFile.file_path,
                )
                .join(IndexedFile, Sequence.file_id == IndexedFile.id)
                .outerjoin(feat_sub, Sequence.id == feat_sub.c.seq_id)
                .options(selectinload(Sequence.features))
                .where(IndexedFile.status == "active")
                .where(
                    or_(
                        seq_sim > 0.1,
                        desc_sim > 0.1,
                        feat_score > 0.1,
                    )
                )
                .order_by(combined.desc())
                .limit(inp.limit)
            )

            # Apply filters
            if topo := inp.filters.get("topology"):
                stmt = stmt.where(Sequence.topology == topo)
            if size_min := inp.filters.get("size_min"):
                stmt = stmt.where(Sequence.size_bp >= int(size_min))
            if size_max := inp.filters.get("size_max"):
                stmt = stmt.where(Sequence.size_bp <= int(size_max))
            if feat_type := inp.filters.get("feature_type"):
                # Unwrap list if LLM sends ["plasmid"] instead of "plasmid"
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
                results.append(
                    SearchResultItem(
                        id=seq.id,
                        name=seq.name,
                        size_bp=seq.size_bp,
                        topology=seq.topology,
                        features=feat_names,
                        file_path=file_path,
                        score=round(float(score), 3),
                    ).model_dump()
                )

        return {
            "results": results,
            "total": len(results),
            "query": inp.query,
        }

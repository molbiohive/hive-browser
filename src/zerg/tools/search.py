"""Search tool — NLP-powered metadata + feature search using pg_trgm."""

from typing import Any

from pydantic import BaseModel, Field

from zerg.tools.base import Tool, ToolInput


class SearchInput(ToolInput):
    query: str = Field(..., description="Search text (name, feature, description)")
    filters: dict[str, Any] = Field(default_factory=dict, description="Optional filters: resistance, topology, size_min, size_max, type, project")
    limit: int = Field(default=20, ge=1, le=100)


class SearchResultItem(BaseModel):
    id: int
    name: str
    size_bp: int
    topology: str
    features: list[str]
    resistance: list[str]
    file_path: str
    score: float


class SearchTool(Tool):
    name = "search"
    description = "Search sequences by name, features, resistance markers, and metadata. Supports fuzzy matching."

    def input_schema(self) -> type[ToolInput]:
        return SearchInput

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        """Execute search against PostgreSQL with pg_trgm fuzzy matching."""
        inp = SearchInput(**params)

        # TODO: build and execute query
        # - trigram similarity on sequences.name, features.name
        # - JSONB containment on sequences.meta
        # - filter by topology, size range, feature type
        # - JOIN features for resistance marker search

        return {
            "results": [],
            "total": 0,
            "query": inp.query,
        }

"""BLAST tool — sequence similarity search using local BLAST+."""

from typing import Any

from pydantic import Field

from zerg.tools.base import Tool, ToolInput


class BlastInput(ToolInput):
    sequence: str = Field(..., description="Query sequence (nucleotide) or sequence name to look up")
    program: str = Field(default="blastn", description="BLAST program: blastn or blastp")
    evalue: float = Field(default=1e-5, description="E-value threshold")
    max_hits: int = Field(default=20, ge=1, le=100)


class BlastTool(Tool):
    name = "blast"
    description = "Find similar sequences using BLAST+ alignment. Accepts raw sequence or a sequence name from the database."

    def input_schema(self) -> type[ToolInput]:
        return BlastInput

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        """Run BLAST+ against the local index and return ranked hits."""
        inp = BlastInput(**params)

        # TODO:
        # 1. If inp.sequence looks like a name, resolve to actual sequence from DB
        # 2. Write query to temp FASTA
        # 3. Run blastn/blastp subprocess
        # 4. Parse XML/tabular output
        # 5. Return ranked hits with identity%, coverage, e-value

        return {
            "hits": [],
            "query_length": len(inp.sequence),
            "program": inp.program,
        }

"""Tests for tool RAG: catalog, TF-IDF selection, planning prefix handling."""

from typing import Any
from unittest.mock import AsyncMock

import pytest

from hive.llm.prompts import build_tool_catalog
from hive.llm.tool_rag import ToolRAG, _cosine_sim, _tfidf_vector, _build_tfidf, _tokenize
from hive.tools.base import Tool


# ── Fixtures ──


class FakeTool(Tool):
    """Minimal tool for testing."""

    widget = "text"
    tags = {"llm"}

    def __init__(self, name: str, description: str, **_):
        self.name = name
        self.description = description

    async def execute(self, params: dict[str, Any], **kw) -> dict[str, Any]:
        return {"ok": True}


@pytest.fixture()
def tools():
    return [
        FakeTool("search", "Search sequences by name, features, and metadata."),
        FakeTool("blast", "Find similar sequences using BLAST+ alignment."),
        FakeTool("translate", "Translate a DNA or RNA sequence to protein."),
        FakeTool("extract", "Extract a subsequence by feature or region."),
        FakeTool("profile", "Show full details of a specific sequence."),
        FakeTool("digest", "Find restriction enzyme cut sites and fragment sizes."),
        FakeTool("gc", "Calculate GC content and nucleotide composition."),
        FakeTool("revcomp", "Get the reverse complement of a DNA sequence."),
        FakeTool("transcribe", "Transcribe DNA to mRNA."),
        FakeTool("align", "Align multiple sequences using MAFFT."),
        FakeTool("parts", "Look up a part by PID, or list parts on a sequence."),
    ]


@pytest.fixture()
def rag(tools):
    return ToolRAG(tools=tools, threshold=0.2, top_k=5)


# ── Catalog ──


class TestCatalog:
    def test_catalog_format(self, tools):
        catalog = build_tool_catalog(tools)
        lines = catalog.strip().split("\n")
        assert len(lines) == len(tools)
        for line in lines:
            assert line.startswith("- ")
            assert ": " in line

    def test_catalog_uses_description(self, tools):
        """Catalog should use short description, not guidelines."""
        catalog = build_tool_catalog(tools)
        assert "Search sequences by name" in catalog
        assert "BLAST+" in catalog


# ── TF-IDF Helpers ──


class TestTFIDF:
    def test_tokenize(self):
        tokens = _tokenize("Search DNA/RNA sequences")
        assert tokens == ["search", "dna", "rna", "sequences"]

    def test_build_tfidf_idf_values(self):
        docs = [["search", "dna"], ["search", "protein"], ["blast", "dna"]]
        idf = _build_tfidf(docs)
        # "search" appears in 2/3 docs, "blast" in 1/3
        assert idf["blast"] > idf["search"]

    def test_cosine_sim_identical(self):
        vec = {"a": 1.0, "b": 2.0}
        assert _cosine_sim(vec, vec) == pytest.approx(1.0)

    def test_cosine_sim_orthogonal(self):
        a = {"x": 1.0}
        b = {"y": 1.0}
        assert _cosine_sim(a, b) == pytest.approx(0.0)


# ── TF-IDF Selection ──


class TestTFIDFSelection:
    def test_search_query_matches_search(self, rag):
        selected = rag._select_tfidf("search for sequences by name")
        names = [t.name for t in selected]
        assert "search" in names

    def test_translate_query_matches_translate(self, rag):
        selected = rag._select_tfidf("translate DNA to protein")
        names = [t.name for t in selected]
        assert "translate" in names

    def test_blast_query_matches_blast(self, rag):
        selected = rag._select_tfidf("find similar sequences using alignment")
        names = [t.name for t in selected]
        assert "blast" in names

    def test_minimum_3_tools(self, tools):
        """Even with high threshold, at least 3 tools returned."""
        rag = ToolRAG(tools=tools, threshold=0.99, top_k=5)
        selected = rag._select_tfidf("something very specific")
        assert len(selected) >= 3

    def test_respects_top_k(self, tools):
        rag = ToolRAG(tools=tools, threshold=0.0, top_k=3)
        selected = rag._select_tfidf("search blast translate extract")
        assert len(selected) == 3


# ── Planning ──


class TestPlan:
    def _mock_llm(self, content):
        client = AsyncMock()
        client.chat = AsyncMock(return_value={
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 10},
        })
        return client

    async def test_answer_prefix(self, rag):
        llm = self._mock_llm("ANSWER: GFP is Green Fluorescent Protein.")
        prefix, content, usage = await rag.plan("What is GFP?", llm)
        assert prefix == "ANSWER"
        assert "Green Fluorescent Protein" in content
        assert usage["in"] == 50

    async def test_action_prefix(self, rag):
        llm = self._mock_llm("ACTION: Search for GFP sequences in the database.")
        prefix, content, usage = await rag.plan("find GFP", llm)
        assert prefix == "ACTION"
        assert "Search" in content

    async def test_missing_prefix_defaults_to_action(self, rag):
        llm = self._mock_llm("Search for GFP sequences and extract the promoter.")
        prefix, content, _ = await rag.plan("find GFP", llm)
        assert prefix == "ACTION"

    async def test_case_insensitive_prefix(self, rag):
        llm = self._mock_llm("answer: This is a simple question.")
        prefix, _, _ = await rag.plan("hello", llm)
        assert prefix == "ANSWER"

    async def test_plan_passes_history(self, rag):
        llm = self._mock_llm("ANSWER: Yes.")
        history = [{"role": "user", "content": "prev"}, {"role": "assistant", "content": "ok"}]
        await rag.plan("follow up", llm, history=history)
        call_args = llm.chat.call_args[0][0]
        # system + 2 history + user = 4 messages
        assert len(call_args) == 4

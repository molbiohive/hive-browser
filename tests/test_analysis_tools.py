"""Tests for pure analysis tools (no DB required)."""

import pytest

from hive.tools.translate import TranslateTool
from hive.tools.transcribe import TranscribeTool
from hive.tools.digest import DigestTool
from hive.tools.gc import GCTool
from hive.tools.revcomp import RevCompTool
from hive.tools.extract import _slice_sequence
from hive.tools.search import _parse_bool_query


# ── Translate ──


class TestTranslate:
    @pytest.fixture()
    def tool(self):
        return TranslateTool()

    async def test_basic_orf(self, tool):
        result = await tool.execute({"sequence": "ATGAAATTTGCCTGA"})
        assert result["protein"] == "MKFA*"
        assert result["protein_length"] == 5
        assert result["nucleotide_length"] == 15
        assert result["complete"] is True
        assert result["stop_codons"] == 1
        assert result["codon_table"] == 1

    async def test_rna_input(self, tool):
        result = await tool.execute({"sequence": "AUGAAAUUUGCCUGA"})
        assert result["protein"] == "MKFA*"
        assert result["complete"] is True

    async def test_incomplete_orf(self, tool):
        # No start Met, no trailing stop
        result = await tool.execute({"sequence": "AAATTTGCC"})
        assert result["protein"] == "KFA"
        assert result["complete"] is False
        assert result["stop_codons"] == 0

    async def test_bacterial_table(self, tool):
        # GTG = V in standard, but table 11 start codon
        result = await tool.execute({"sequence": "ATGAAATGA", "table": 11})
        assert result["codon_table"] == 11

    async def test_too_short(self, tool):
        result = await tool.execute({"sequence": "AT"})
        assert "error" in result

    async def test_whitespace_handling(self, tool):
        result = await tool.execute({"sequence": "ATG AAA TTT TGA"})
        assert result["protein"] == "MKF*"

    async def test_format_result(self, tool):
        result = {"protein_length": 10, "complete": True}
        assert "10 amino acids" in tool.format_result(result)
        assert "complete ORF" in tool.format_result(result)

    async def test_format_result_error(self, tool):
        assert tool.format_result({"error": "bad"}) == "Error: bad"


# ── Transcribe ──


class TestTranscribe:
    @pytest.fixture()
    def tool(self):
        return TranscribeTool()

    async def test_basic(self, tool):
        result = await tool.execute({"sequence": "ATGCATGC"})
        assert result["rna"] == "AUGCAUGC"
        assert result["length"] == 8

    async def test_lowercase(self, tool):
        result = await tool.execute({"sequence": "atgc"})
        assert result["rna"] == "AUGC"

    async def test_empty(self, tool):
        result = await tool.execute({"sequence": ""})
        assert "error" in result

    async def test_whitespace(self, tool):
        result = await tool.execute({"sequence": "ATG C"})
        assert result["rna"] == "AUGC"

    async def test_format_result(self, tool):
        assert "8 nt" in tool.format_result({"length": 8})


# ── Digest ──


class TestDigest:
    @pytest.fixture()
    def tool(self):
        return DigestTool()

    async def test_ecori_single_site(self, tool):
        # EcoRI recognizes GAATTC
        seq = "AAAGAATTCAAA"
        result = await tool.execute({"sequence": seq, "enzymes": ["EcoRI"], "circular": False})
        assert result["total_cuts"] == 1
        assert len(result["fragments"]) == 2
        assert sum(result["fragments"]) == len(seq)
        assert result["sequence_length"] == 12

    async def test_no_cuts(self, tool):
        seq = "AAAAAAAAAA"
        result = await tool.execute({"sequence": seq, "enzymes": ["EcoRI"], "circular": False})
        assert result["total_cuts"] == 0
        assert result["fragments"] == [10]

    async def test_circular_digest(self, tool):
        # Circular fragment sizes should sum to sequence length
        seq = "GAATTCAAAAAAGAATTCAAAAAA"
        result = await tool.execute({"sequence": seq, "enzymes": ["EcoRI"], "circular": True})
        assert result["circular"] is True
        assert sum(result["fragments"]) == len(seq)

    async def test_multiple_enzymes(self, tool):
        # EcoRI (GAATTC) and BamHI (GGATCC)
        seq = "GAATTCAAAAGGATCCAAAA"
        result = await tool.execute(
            {"sequence": seq, "enzymes": ["EcoRI", "BamHI"], "circular": False}
        )
        assert result["total_cuts"] == 2
        assert len(result["enzymes"]) == 2
        assert sum(result["fragments"]) == len(seq)

    async def test_invalid_enzyme(self, tool):
        result = await tool.execute(
            {"sequence": "ATGC", "enzymes": ["NotAnEnzyme"]}
        )
        assert "error" in result

    async def test_empty_sequence(self, tool):
        result = await tool.execute({"sequence": "", "enzymes": ["EcoRI"]})
        assert "error" in result

    async def test_format_result(self, tool):
        result = {"total_cuts": 2, "fragments": [500, 300]}
        fmt = tool.format_result(result)
        assert "2 cut(s)" in fmt
        assert "2 fragment(s)" in fmt


# ── GC Content ──


class TestGC:
    @pytest.fixture()
    def tool(self):
        return GCTool()

    async def test_50_percent(self, tool):
        result = await tool.execute({"sequence": "ATGC"})
        assert result["gc_percent"] == 50.0
        assert result["at_percent"] == 50.0
        assert result["length"] == 4
        assert result["g"] == 1
        assert result["c"] == 1
        assert result["a"] == 1
        assert result["t"] == 1

    async def test_all_gc(self, tool):
        result = await tool.execute({"sequence": "GCGCGC"})
        assert result["gc_percent"] == 100.0

    async def test_all_at(self, tool):
        result = await tool.execute({"sequence": "ATATAT"})
        assert result["gc_percent"] == 0.0

    async def test_empty(self, tool):
        result = await tool.execute({"sequence": ""})
        assert "error" in result

    async def test_whitespace(self, tool):
        result = await tool.execute({"sequence": "AT GC"})
        assert result["gc_percent"] == 50.0
        assert result["length"] == 4

    async def test_format_result(self, tool):
        result = {"gc_percent": 42.5, "length": 100}
        assert "42.5%" in tool.format_result(result)


# ── Reverse Complement ──


class TestRevComp:
    @pytest.fixture()
    def tool(self):
        return RevCompTool()

    async def test_basic(self, tool):
        result = await tool.execute({"sequence": "ATGC"})
        assert result["sequence"] == "GCAT"
        assert result["length"] == 4

    async def test_palindrome(self, tool):
        # GAATTC is a palindrome (EcoRI site)
        result = await tool.execute({"sequence": "GAATTC"})
        assert result["sequence"] == "GAATTC"

    async def test_lowercase(self, tool):
        result = await tool.execute({"sequence": "atgc"})
        assert result["sequence"] == "GCAT"

    async def test_empty(self, tool):
        result = await tool.execute({"sequence": ""})
        assert "error" in result

    async def test_double_revcomp_identity(self, tool):
        seq = "ATGCGATCGTAGC"
        r1 = await tool.execute({"sequence": seq})
        r2 = await tool.execute({"sequence": r1["sequence"]})
        assert r2["sequence"] == seq

    async def test_format_result(self, tool):
        assert "10 bp" in tool.format_result({"length": 10})


# ── Extract: _slice_sequence ──


class TestSliceSequence:
    def test_normal_slice(self):
        assert _slice_sequence("ABCDEFGHIJ", 2, 5, "linear") == "CDE"

    def test_full_sequence(self):
        assert _slice_sequence("ABCDE", 0, 5, "linear") == "ABCDE"

    def test_circular_wraparound(self):
        # start=8, end=3 on circular → last 2 + first 3
        assert _slice_sequence("ABCDEFGHIJ", 8, 3, "circular") == "IJABC"

    def test_linear_no_wrap(self):
        # start > end on linear → empty (no wrap support)
        result = _slice_sequence("ABCDEFGHIJ", 8, 3, "linear")
        assert result == ""  # seq[8:3] = ""

    def test_zero_length(self):
        assert _slice_sequence("ABCDE", 3, 3, "linear") == ""

    def test_single_base(self):
        assert _slice_sequence("ABCDE", 2, 3, "linear") == "C"


class TestParseBoolQuery:
    def test_single_term(self):
        assert _parse_bool_query("GFP") == (["GFP"], "single")

    def test_and_two_terms(self):
        assert _parse_bool_query("KanR && circular") == (["KanR", "circular"], "and")

    def test_and_three_terms(self):
        terms, op = _parse_bool_query("KanR && circular && promoter")
        assert op == "and"
        assert terms == ["KanR", "circular", "promoter"]

    def test_or_two_terms(self):
        assert _parse_bool_query("GFP || RFP") == (["GFP", "RFP"], "or")

    def test_empty_parts_stripped(self):
        terms, op = _parse_bool_query("KanR &&  && GFP")
        assert op == "and"
        assert terms == ["KanR", "GFP"]

    def test_single_term_with_dangling_op(self):
        terms, op = _parse_bool_query("GFP &&")
        assert op == "single"
        assert terms == ["GFP"]

    def test_whitespace_handling(self):
        terms, op = _parse_bool_query("  KanR  &&  circular  ")
        assert terms == ["KanR", "circular"]
        assert op == "and"

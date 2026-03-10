"""Tests for pure analysis tools (no DB required)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hive.tools.digest import DigestTool
from hive.tools.extract import _slice_sequence
from hive.tools.gc import GCTool
from hive.tools.resolve import resolve_input
from hive.tools.revcomp import RevCompTool
from hive.tools.search import _parse_bool_query
from hive.tools.sites import SitesTool
from hive.tools.transcribe import TranscribeTool
from hive.tools.translate import TranslateTool

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


def _mock_enzymes():
    """Build mock enzyme dict for digest tests."""
    from types import SimpleNamespace

    ecori = SimpleNamespace(
        name="EcoRI", site="GAATTC", cut5=1, cut3=-1,
        overhang=-4, length=6, is_palindrome=True, is_blunt=False,
    )
    bamhi = SimpleNamespace(
        name="BamHI", site="GGATCC", cut5=1, cut3=-1,
        overhang=-4, length=6, is_palindrome=True, is_blunt=False,
    )
    return {"ECORI": ecori, "BAMHI": bamhi}


class TestDigest:
    @pytest.fixture()
    def tool(self):
        return DigestTool()

    @pytest.fixture(autouse=True)
    def _mock_db(self):
        enzymes = _mock_enzymes()
        mock_factory = MagicMock()
        mock_session = AsyncMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_factory
        with (
            patch("hive.tools.digest.db.async_session_factory", mock_factory),
            patch("hive.cloning.enzymes.load_enzymes", AsyncMock(return_value=enzymes)),
        ):
            yield

    async def test_ecori_single_site(self, tool):
        # EcoRI recognizes GAATTC
        seq = "AAAGAATTCAAA"
        result = await tool.execute({"sequence": seq, "reactions": ["EcoRI"], "circular": False})
        rxn = result["reactions"][0]
        assert rxn["total_cuts"] == 1
        assert len(rxn["fragments"]) == 2
        assert sum(rxn["fragments"]) == len(seq)
        assert result["sequence_length"] == 12

    async def test_no_cuts(self, tool):
        seq = "AAAAAAAAAA"
        result = await tool.execute({"sequence": seq, "reactions": ["EcoRI"], "circular": False})
        rxn = result["reactions"][0]
        assert rxn["total_cuts"] == 0
        assert rxn["fragments"] == [10]

    async def test_circular_digest(self, tool):
        # Circular fragment sizes should sum to sequence length
        seq = "GAATTCAAAAAAGAATTCAAAAAA"
        result = await tool.execute({"sequence": seq, "reactions": ["EcoRI"], "circular": True})
        assert result["circular"] is True
        assert sum(result["reactions"][0]["fragments"]) == len(seq)

    async def test_co_digestion(self, tool):
        # EcoRI (GAATTC) and BamHI (GGATCC) in one reaction
        seq = "GAATTCAAAAGGATCCAAAA"
        result = await tool.execute(
            {"sequence": seq, "reactions": ["EcoRI+BamHI"], "circular": False}
        )
        rxn = result["reactions"][0]
        assert rxn["total_cuts"] == 2
        assert len(rxn["enzymes"]) == 2
        assert sum(rxn["fragments"]) == len(seq)

    async def test_separate_reactions(self, tool):
        # Two separate reactions -- two gel lanes
        seq = "GAATTCAAAAGGATCCAAAA"
        result = await tool.execute(
            {"sequence": seq, "reactions": ["EcoRI", "BamHI"], "circular": False}
        )
        assert len(result["reactions"]) == 2
        assert result["reactions"][0]["name"] == "EcoRI"
        assert result["reactions"][1]["name"] == "BamHI"
        # Each single enzyme should produce 1 cut
        assert result["reactions"][0]["total_cuts"] == 1
        assert result["reactions"][1]["total_cuts"] == 1
        # Gel should have ladder + 2 sample lanes
        assert len(result["gel_data"]["lanes"]) == 3

    async def test_invalid_enzyme(self, tool):
        result = await tool.execute(
            {"sequence": "ATGC", "reactions": ["NotAnEnzyme"]}
        )
        assert "error" in result

    async def test_empty_sequence(self, tool):
        result = await tool.execute({"sequence": "", "reactions": ["EcoRI"]})
        assert "error" in result

    async def test_format_result(self, tool):
        result = {"reactions": [{"name": "EcoRI", "total_cuts": 2, "fragments": [500, 300]}]}
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


# ── resolve_input ──


class TestResolveInput:
    async def test_raw_sequence_passthrough(self):
        session = AsyncMock()
        seq, meta = await resolve_input(session, "ATGCATGC")
        assert seq == "ATGCATGC"
        assert meta == {"source": "raw"}

    async def test_raw_whitespace_stripped(self):
        session = AsyncMock()
        seq, meta = await resolve_input(session, "  ATGC  ")
        assert seq == "ATGC"
        assert meta["source"] == "raw"

    async def test_sid_resolution(self):
        mock_seq = MagicMock()
        mock_seq.sequence = "GATTACA"
        mock_seq.id = 42
        mock_seq.name = "TestSeq"

        session = AsyncMock()
        with patch("hive.tools.resolve.resolve_sequence", return_value=mock_seq) as mock_rs:
            seq, meta = await resolve_input(session, "sid:42")
            assert seq == "GATTACA"
            assert meta == {"source": "sid", "sid": 42, "name": "TestSeq"}
            mock_rs.assert_called_once_with(session, sid=42)

    async def test_pid_resolution(self):
        mock_name = MagicMock()
        mock_name.name = "GFP"
        mock_part = MagicMock()
        mock_part.sequence = "ATGGTGAGC"
        mock_part.id = 7
        mock_part.names = [mock_name]

        session = AsyncMock()
        with patch("hive.tools.resolve.resolve_part", return_value=mock_part) as mock_rp:
            seq, meta = await resolve_input(session, "pid:7")
            assert seq == "ATGGTGAGC"
            assert meta["source"] == "pid"
            assert meta["pid"] == 7
            assert meta["names"] == ["GFP"]
            mock_rp.assert_called_once_with(session, pid=7, load_names=True)

    async def test_sid_not_found_raises(self):
        session = AsyncMock()
        with (
            patch("hive.tools.resolve.resolve_sequence", return_value=None),
            pytest.raises(ValueError, match="SID 999"),
        ):
            await resolve_input(session, "sid:999")

    async def test_pid_not_found_raises(self):
        session = AsyncMock()
        with (
            patch("hive.tools.resolve.resolve_part", return_value=None),
            pytest.raises(ValueError, match="PID 999"),
        ):
            await resolve_input(session, "pid:999")

    async def test_case_insensitive(self):
        mock_seq = MagicMock()
        mock_seq.sequence = "ATGC"
        mock_seq.id = 1
        mock_seq.name = "Test"
        session = AsyncMock()
        with patch("hive.tools.resolve.resolve_sequence", return_value=mock_seq):
            seq, meta = await resolve_input(session, "SID:1")
            assert meta["source"] == "sid"


# ── Universal input: tools return error for missing SID/PID without DB ──


class TestUniversalInputNoDB:
    """Verify analysis tools handle sid:/pid: gracefully without a live DB."""

    async def test_translate_raw_still_works(self):
        tool = TranslateTool()
        result = await tool.execute({"sequence": "ATGAAATTTGCCTGA"})
        assert result["protein"] == "MKFA*"

    async def test_digest_no_db_returns_error(self):
        tool = DigestTool()
        result = await tool.execute(
            {"sequence": "AAAGAATTCAAA", "reactions": ["EcoRI"], "circular": False}
        )
        assert "error" in result

    async def test_gc_raw_still_works(self):
        tool = GCTool()
        result = await tool.execute({"sequence": "ATGC"})
        assert result["gc_percent"] == 50.0

    async def test_revcomp_raw_still_works(self):
        tool = RevCompTool()
        result = await tool.execute({"sequence": "ATGC"})
        assert result["sequence"] == "GCAT"

    async def test_transcribe_raw_still_works(self):
        tool = TranscribeTool()
        result = await tool.execute({"sequence": "ATGC"})
        assert result["rna"] == "AUGC"


# ── Sites (inverse digest) ──


class TestSites:
    @pytest.fixture()
    def tool(self):
        return SitesTool()

    @pytest.fixture(autouse=True)
    def _mock_db(self):
        enzymes = _mock_enzymes()
        mock_factory = MagicMock()
        mock_session = AsyncMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_factory
        with (
            patch("hive.tools.sites.db.async_session_factory", mock_factory),
            patch("hive.cloning.enzymes.load_enzymes", AsyncMock(return_value=enzymes)),
        ):
            yield

    async def test_ecori_site(self, tool):
        seq = "AAAGAATTCAAA"
        result = await tool.execute({"sequence": seq, "circular": False})
        assert result["cutters_found"] >= 1
        names = [c["name"] for c in result["cutters"]]
        assert "EcoRI" in names

    async def test_no_cutters(self, tool):
        seq = "AAAAAAAAAA"
        result = await tool.execute({"sequence": seq, "circular": False})
        assert result["cutters_found"] == 0
        assert result["cutters"] == []

    async def test_max_cuts_filter(self, tool):
        # Two EcoRI sites -- max_cuts=1 should exclude it
        seq = "GAATTCAAAAAAGAATTCAAAAAA"
        result = await tool.execute(
            {"sequence": seq, "circular": False, "max_cuts": 1}
        )
        ecori_hits = [c for c in result["cutters"] if c["name"] == "EcoRI"]
        assert len(ecori_hits) == 0

    async def test_unique_cutters(self, tool):
        # One EcoRI site, one BamHI site -- both should appear with max_cuts=1
        seq = "AAAGAATTCAAAGGATCCAAA"
        result = await tool.execute(
            {"sequence": seq, "circular": False, "max_cuts": 1}
        )
        names = {c["name"] for c in result["cutters"]}
        assert "EcoRI" in names
        assert "BamHI" in names

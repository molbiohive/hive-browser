"""Tests for file parsers."""

from pathlib import Path

import pytest

from zerg.parsers.base import ParseResult
from zerg.parsers.genbank import parse_genbank
from zerg.parsers.fasta import parse_fasta
from zerg.parsers import PARSERS, BIOPYTHON_PARSERS

FIXTURES = Path(__file__).parent / "fixtures"


class TestGenbankParser:
    def test_parse_basic(self):
        result = parse_genbank(FIXTURES / "test_plasmid.gb")

        assert isinstance(result, ParseResult)
        assert result.name == "pTest"
        assert result.topology == "circular"
        assert result.size_bp == 120
        assert len(result.sequence) == 120

    def test_parse_features(self):
        result = parse_genbank(FIXTURES / "test_plasmid.gb")

        assert len(result.features) == 3

        names = {f.name for f in result.features}
        assert "T7_promoter" in names
        assert "GFP_mini" in names
        assert "T7_term" in names

    def test_feature_types(self):
        result = parse_genbank(FIXTURES / "test_plasmid.gb")

        type_map = {f.name: f.type for f in result.features}
        assert type_map["T7_promoter"] == "promoter"
        assert type_map["GFP_mini"] == "CDS"
        assert type_map["T7_term"] == "terminator"

    def test_feature_positions(self):
        result = parse_genbank(FIXTURES / "test_plasmid.gb")

        gfp = next(f for f in result.features if f.name == "GFP_mini")
        assert gfp.start == 39  # 0-indexed (GenBank is 1-indexed, Biopython converts)
        assert gfp.end == 108
        assert gfp.strand == 1

    def test_feature_qualifiers(self):
        result = parse_genbank(FIXTURES / "test_plasmid.gb")

        gfp = next(f for f in result.features if f.name == "GFP_mini")
        assert "gene" in gfp.qualifiers
        assert gfp.qualifiers["gene"] == "GFP"

    def test_description(self):
        result = parse_genbank(FIXTURES / "test_plasmid.gb")
        assert "Test plasmid for unit testing" in result.description

    def test_extract_filter(self):
        result = parse_genbank(FIXTURES / "test_plasmid.gb", extract=["sequence"])
        assert result.features == []
        assert len(result.sequence) == 120


class TestFastaParser:
    def test_parse_basic(self):
        result = parse_fasta(FIXTURES / "test_sequence.fasta")

        assert isinstance(result, ParseResult)
        assert result.name == "GFP_coding_sequence"
        assert result.topology == "linear"
        assert result.size_bp == 240
        assert result.features == []
        assert result.primers == []

    def test_description(self):
        result = parse_fasta(FIXTURES / "test_sequence.fasta")
        assert "Green fluorescent protein" in result.description

    def test_sequence_content(self):
        result = parse_fasta(FIXTURES / "test_sequence.fasta")
        assert result.sequence.startswith("ATGGTGAGCAAGGGCGAGGAG")


class TestParserRegistry:
    def test_parsers_registered(self):
        assert "sgffp" in PARSERS
        assert "biopython" in PARSERS

    def test_biopython_parsers(self):
        assert "gb" in BIOPYTHON_PARSERS
        assert "gbk" in BIOPYTHON_PARSERS
        assert "fasta" in BIOPYTHON_PARSERS
        assert "fa" in BIOPYTHON_PARSERS

    def test_biopython_genbank(self):
        parser = BIOPYTHON_PARSERS["gb"]
        result = parser(FIXTURES / "test_plasmid.gb")
        assert result.name == "pTest"

    def test_biopython_fasta(self):
        parser = BIOPYTHON_PARSERS["fasta"]
        result = parser(FIXTURES / "test_sequence.fasta")
        assert result.name == "GFP_coding_sequence"

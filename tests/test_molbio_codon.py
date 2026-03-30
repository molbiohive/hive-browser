"""Tests for molbio/codon -- codon usage analysis."""

import pytest

from hive.molbio.codon import codon_usage, rare_codons


class TestCodonUsage:
    def test_basic(self):
        # ATG AAA TTT GCC TGA = 5 codons
        seq = "ATGAAATTTGCCTGA"
        result = codon_usage(seq)
        assert len(result) > 0
        by_codon = {r["codon"]: r for r in result}
        assert by_codon["ATG"]["count"] == 1
        assert by_codon["AAA"]["count"] == 1
        assert by_codon["TTT"]["count"] == 1
        assert by_codon["GCC"]["count"] == 1

    def test_frequencies_sum_to_one(self):
        seq = "ATGAAATTTGCCTGA"
        result = codon_usage(seq)
        total = sum(r["frequency"] for r in result)
        assert abs(total - 1.0) < 0.01

    def test_rscu_equal_usage(self):
        # Use all 4 Ala codons equally: GCT GCC GCA GCG
        seq = "GCTGCCGCAGCG"
        result = codon_usage(seq)
        ala = [r for r in result if r["amino_acid"] == "A"]
        for a in ala:
            if a["count"] > 0:
                assert a["rscu"] == 1.0

    def test_unknown_table(self):
        with pytest.raises(ValueError, match="Unknown codon table"):
            codon_usage("ATGATG", table=999)

    def test_rna_input(self):
        result = codon_usage("AUGAAAUUUGCCUGA")
        by_codon = {r["codon"]: r for r in result}
        assert by_codon["ATG"]["count"] == 1


class TestRareCodons:
    def test_returns_only_used(self):
        seq = "ATGAAATTTGCCTGA"
        result = rare_codons(seq)
        for r in result:
            assert r["count"] > 0

    def test_excludes_stops(self):
        seq = "ATGAAATTTGCCTGA"
        result = rare_codons(seq)
        for r in result:
            assert r["amino_acid"] != "*"

    def test_threshold(self):
        seq = "ATGAAATTTGCCTGA"
        result = rare_codons(seq, threshold=0.5)
        for r in result:
            assert r["frequency"] < 0.5

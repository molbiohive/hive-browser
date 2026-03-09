"""Tests for libs/classify -- deterministic part analysis."""

import pytest

from hive.libs.classify import (
    analyze_orf,
    analyze_primer,
    classify_part,
    gc_content,
)


class TestGcContent:
    def test_all_gc(self):
        assert gc_content("GCGCGC") == 1.0

    def test_all_at(self):
        assert gc_content("ATATAT") == 0.0

    def test_mixed(self):
        assert gc_content("ATGC") == 0.5

    def test_empty(self):
        assert gc_content("") == 0.0

    def test_lowercase(self):
        assert gc_content("atgc") == 0.5


class TestAnalyzeOrf:
    def test_complete_orf(self):
        # ATG + 3 codons + TAA
        seq = "ATGAAAGCCTAA"
        result = analyze_orf(seq)
        assert result["orf_status"] == "complete"
        assert result["has_start"] == "true"
        assert result["has_stop"] == "true"
        assert result["internal_stops"] == "0"
        assert result["codon_count"] == "4"
        assert result["in_frame"] == "true"

    def test_no_start(self):
        seq = "GGGAAAGCCTAA"
        result = analyze_orf(seq)
        assert result["orf_status"] == "no_start"
        assert result["has_start"] == "false"
        assert result["has_stop"] == "true"

    def test_no_stop(self):
        seq = "ATGAAAGCCGGG"
        result = analyze_orf(seq)
        assert result["orf_status"] == "no_stop"
        assert result["has_start"] == "true"
        assert result["has_stop"] == "false"

    def test_partial(self):
        seq = "GGGAAAGCCGGG"
        result = analyze_orf(seq)
        assert result["orf_status"] == "partial"

    def test_internal_stops(self):
        # ATG + TAA (internal) + GCC + TAA (terminal)
        seq = "ATGTAAGCCTAA"
        result = analyze_orf(seq)
        assert result["orf_status"] == "internal_stops"
        assert result["internal_stops"] == "1"

    def test_out_of_frame(self):
        seq = "ATGAA"  # 5 nt, not divisible by 3
        result = analyze_orf(seq)
        assert result["in_frame"] == "false"

    def test_too_short(self):
        seq = "AT"
        result = analyze_orf(seq)
        assert result["orf_status"] == "too_short"

    def test_minimal_orf(self):
        # ATG + stop = 2 codons, smallest possible complete ORF
        seq = "ATGTAA"
        result = analyze_orf(seq)
        assert result["orf_status"] == "complete"
        assert result["codon_count"] == "2"


class TestAnalyzePrimer:
    def test_short_primer_wallace(self):
        # 10 nt primer, should use Wallace rule
        seq = "ATGCATGCAT"  # 6 AT + 4 GC
        result = analyze_primer(seq)
        assert result["tm"] == "28.0"  # 2*6 + 4*4

    def test_long_primer_salt_adjusted(self):
        # 20 nt primer
        seq = "ATGCATGCATGCATGCATGC"  # 10 AT + 10 GC
        result = analyze_primer(seq)
        assert "tm" in result
        tm = float(result["tm"])
        assert 40 < tm < 80  # sanity range

    def test_gc_content_included(self):
        seq = "ATGCATGC"
        result = analyze_primer(seq)
        assert result["gc_content"] == "0.500"

    def test_empty(self):
        assert analyze_primer("") == {}


class TestClassifyPart:
    def test_cds_includes_orf(self):
        seq = "ATGAAAGCCTAA"
        result = classify_part(seq, "CDS")
        assert "gc_content" in result
        assert "length" in result
        assert "orf_status" in result
        assert result["orf_status"] == "complete"

    def test_primer_includes_tm(self):
        seq = "ATGCATGCATGCATGCATGC"
        result = classify_part(seq, "primer_bind")
        assert "tm" in result
        assert "gc_content" in result

    def test_promoter_basic_only(self):
        seq = "TATAATGCAGCTGGCACGACAG"
        result = classify_part(seq, "promoter")
        assert "gc_content" in result
        assert "length" in result
        # No ORF or Tm analysis for promoters
        assert "orf_status" not in result
        assert "tm" not in result

    def test_values_are_strings(self):
        result = classify_part("ATGAAAGCCTAA", "CDS")
        for k, v in result.items():
            assert isinstance(v, str), f"{k} is not a string: {type(v)}"

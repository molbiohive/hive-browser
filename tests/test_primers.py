"""Tests for cloning/primers -- primer binding site prediction."""

import pytest

from hive.cloning.primers import find_primer_sites


def _primer(id: int, name: str, sequence: str) -> dict:
    return {"id": id, "name": name, "sequence": sequence}


class TestForwardBinding:
    """Primer binds on the sense strand (strand=1)."""

    def test_exact_match(self):
        #                          0         1         2
        #                          0123456789012345678901234567
        seq = "AAAAAAAAAA" + "GCTAGCATGCTA" + "AAAAAAAAAA"
        primer = _primer(1, "FWD", "GCTAGCATGCTA")
        hits = find_primer_sites(seq, [primer], circular=False, anchor_len=8)
        fwd = [h for h in hits if h["strand"] == 1]
        assert len(fwd) == 1
        assert fwd[0]["primer_id"] == 1
        assert fwd[0]["start"] == 10
        assert fwd[0]["strand"] == 1
        assert fwd[0]["primer_length"] == 12

    def test_anchor_match_only(self):
        """Only the 3' anchor needs to match."""
        seq = "AAAAAAAAAA" + "XXXXCATGCTAG" + "AAAAAAAAAA"
        primer = _primer(1, "FWD", "ZZZZCATGCTAG")
        hits = find_primer_sites(seq, [primer], circular=False, anchor_len=8)
        fwd = [h for h in hits if h["strand"] == 1]
        assert len(fwd) == 1
        assert fwd[0]["start"] == 10

    def test_no_match(self):
        seq = "AAAAAAAAAA" * 5
        primer = _primer(1, "FWD", "ATCGATCGATCG")
        hits = find_primer_sites(seq, [primer], circular=False, anchor_len=8)
        assert len(hits) == 0


class TestReverseBinding:
    """Primer binds on the antisense strand (strand=-1)."""

    def test_rc_match(self):
        # Primer: ATCGATCG -> RC: CGATCGAT
        # Place RC of anchor on the sense strand
        seq = "AAAAAAAAAA" + "CGATCGAT" + "AAAAAAAAAA"
        primer = _primer(1, "REV", "ATCGATCG")
        hits = find_primer_sites(seq, [primer], circular=False, anchor_len=8)
        rev_hits = [h for h in hits if h["strand"] == -1]
        assert len(rev_hits) == 1
        assert rev_hits[0]["start"] == 10

    def test_forward_and_reverse(self):
        """Palindromic anchor matches both strands."""
        # AATTAATT is its own reverse complement
        seq = "CCCCCCCCCC" + "AATTAATT" + "CCCCCCCCCC"
        primer = _primer(1, "BOTH", "AATTAATT")
        hits = find_primer_sites(seq, [primer], circular=False, anchor_len=8)
        strands = {h["strand"] for h in hits}
        assert strands == {1, -1}


class TestCircular:
    """Circular sequence wrap-around detection."""

    def test_wrap_around_forward(self):
        # Primer anchor spans the origin: last 4 bases + first 4 bases
        # Anchor (8bp): "ATCGATCG"
        # Place "ATCG" at end, "ATCG" at start
        seq = "ATCGAAAAAAAAAAAAAAAAAAAAAAAAAAATCG"
        primer = _primer(1, "WRAP", "ATCGATCGATCG")  # 12bp, anchor=ATCGATCG
        hits = find_primer_sites(seq, [primer], circular=True, anchor_len=8)
        fwd = [h for h in hits if h["strand"] == 1]
        assert len(fwd) >= 1
        # Position should be near the origin

    def test_linear_no_wrap(self):
        """Same sequence as above but linear -- should NOT find wrap-around."""
        seq = "ATCGAAAAAAAAAAAAAAAAAAAAAAAAAAATCG"
        primer = _primer(1, "WRAP", "ATCGATCGATCG")
        hits = find_primer_sites(seq, [primer], circular=False, anchor_len=8)
        assert len(hits) == 0


class TestMultiplePrimers:
    """Multiple primers scanned at once."""

    def test_two_primers(self):
        seq = "AAAAAAAAAA" + "ATCGATCG" + "TTTTTTTTTT" + "GCTAGCTA" + "AAAAAAAAAA"
        primers = [
            _primer(1, "P1", "ATCGATCG"),
            _primer(2, "P2", "GCTAGCTA"),
        ]
        hits = find_primer_sites(seq, primers, circular=False, anchor_len=8)
        ids = {h["primer_id"] for h in hits}
        assert 1 in ids
        assert 2 in ids


class TestEdgeCases:
    """Edge cases and validation."""

    def test_empty_sequence(self):
        primer = _primer(1, "P", "ATCGATCG")
        hits = find_primer_sites("", [primer], circular=False)
        assert hits == []

    def test_empty_primers(self):
        hits = find_primer_sites("ATCGATCG", [], circular=False)
        assert hits == []

    def test_short_primer_skipped(self):
        """Primers shorter than anchor_len are skipped."""
        primer = _primer(1, "SHORT", "ATCG")
        hits = find_primer_sites("ATCGATCGATCG", [primer], circular=False, anchor_len=8)
        assert hits == []

    def test_missing_sequence_field(self):
        """Primer dict without 'sequence' key is skipped."""
        primer = {"id": 1, "name": "BAD"}
        hits = find_primer_sites("ATCGATCG", [primer], circular=False)
        assert hits == []

    def test_deduplication(self):
        """Same primer binding at the same position should appear once."""
        seq = "ATCGATCG" * 2  # Repeated pattern
        primer = _primer(1, "P", "ATCGATCG")
        hits = find_primer_sites(seq, [primer], circular=False, anchor_len=8)
        fwd = [h for h in hits if h["strand"] == 1]
        starts = [h["start"] for h in fwd]
        assert len(starts) == len(set(starts))  # no duplicates

"""Tests for molbio/orf -- 6-frame ORF scanner."""

from hive.molbio.orf import find_orfs


class TestFindOrfs:
    def test_complete_orf(self):
        # ATG + 10 codons + TAA = 36 nt
        seq = "ATGAAAGCCGGGTTTAGCAAAGCCGCCTTTGCCTAA"
        orfs = find_orfs(seq, min_length=30)
        assert len(orfs) >= 1
        top = orfs[0]
        assert top["has_start"] is True
        assert top["has_stop"] is True
        assert top["status"] == "complete"
        assert top["frame"] == "+1"
        assert top["protein"].startswith("M")
        assert top["protein"].endswith("*")

    def test_min_length_filter(self):
        # Short ORF: ATG + 2 codons + TAA = 12 nt
        seq = "ATGAAAGCCTAA"
        assert find_orfs(seq, min_length=100) == []
        assert len(find_orfs(seq, min_length=10)) >= 1

    def test_no_start_codon(self):
        seq = "GGGGCCGGGTTTAGCAAAGCCGCCTTTGCCTAA"
        orfs = find_orfs(seq, min_length=10)
        # No ATG -> no ORFs
        assert len(orfs) == 0

    def test_reverse_strand(self):
        # Put ORF on reverse strand by using RC
        # RC of ATGAAAGCCTAA = TTAGGCTTTCAT
        seq = "AAAAATTAGGCTTTCATAAAAAA"
        orfs = find_orfs(seq, min_length=10)
        rev = [o for o in orfs if o["frame"].startswith("-")]
        assert len(rev) >= 1
        assert rev[0]["protein"].startswith("M")

    def test_sorted_by_length(self):
        # Two ORFs of different sizes
        seq = "ATGAAATAA" + "AAAAAAAAAA" + "ATGAAAGCCGCCTAA"
        orfs = find_orfs(seq, min_length=9)
        if len(orfs) >= 2:
            assert orfs[0]["length_nt"] >= orfs[1]["length_nt"]

    def test_multiple_frames(self):
        # Padding shifts the ORF into frame +2
        seq = "A" + "ATGAAAGCCGCCTTTGCCTAA"
        orfs = find_orfs(seq, min_length=10)
        frames = {o["frame"] for o in orfs}
        assert "+2" in frames

    def test_no_stop_partial(self):
        # ORF with start but no stop
        seq = "ATGAAAGCCGCCGCCGCCGCCGCC"
        orfs = find_orfs(seq, min_length=10)
        partial = [o for o in orfs if o["status"] == "no_stop"]
        assert len(partial) >= 1

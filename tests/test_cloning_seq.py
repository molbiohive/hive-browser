"""Tests for hive.cloning.seq -- pure sequence operations."""

import pytest

from hive.cloning.seq import back_transcribe, transcribe, translate


class TestTranscribe:
    def test_basic(self):
        assert transcribe("ATGC") == "AUGC"

    def test_lowercase(self):
        assert transcribe("atgc") == "AUGC"


class TestBackTranscribe:
    def test_basic(self):
        assert back_transcribe("AUGC") == "ATGC"

    def test_roundtrip(self):
        assert back_transcribe(transcribe("ATGCATGC")) == "ATGCATGC"


class TestTranslate:
    def test_standard(self):
        assert translate("ATGAAATTTGCCTGA") == "MKFA*"

    def test_bacterial_table(self):
        result = translate("ATGAAATGA", table=11)
        assert result == "MK*"

    def test_rna_input(self):
        assert translate("AUGAAAUUUGCCUGA") == "MKFA*"

    def test_partial_codon_ignored(self):
        assert translate("ATGAAATT") == "MK"

    def test_single_trailing_base(self):
        assert translate("ATGA") == "M"

    def test_unknown_table(self):
        with pytest.raises(ValueError, match="Unknown codon table"):
            translate("ATG", table=999)

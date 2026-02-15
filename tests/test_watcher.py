"""Tests for the file watcher rule engine."""

from pathlib import Path

from zerg.config import WatcherRule
from zerg.watcher.rules import match_file


def _rules():
    return [
        WatcherRule(match="*.dna", action="parse", parser="sgffp",
                    extract=["sequence", "features", "primers", "notes"]),
        WatcherRule(match="*.gb", action="parse", parser="biopython",
                    extract=["sequence", "features", "description"]),
        WatcherRule(match="*.gbk", action="parse", parser="biopython",
                    extract=["sequence", "features", "description"]),
        WatcherRule(match="*.fasta", action="parse", parser="biopython",
                    extract=["sequence"]),
        WatcherRule(match="*.fa", action="parse", parser="biopython",
                    extract=["sequence"]),
        WatcherRule(match=".*", action="ignore"),
        WatcherRule(match="*.tmp", action="ignore"),
        WatcherRule(match="*.log", action="log", message="Log file detected"),
    ]


class TestRuleMatching:
    def test_match_dna(self):
        result = match_file(Path("plasmid.dna"), _rules())
        assert result.action == "parse"
        assert result.parser == "sgffp"

    def test_match_genbank(self):
        result = match_file(Path("plasmid.gb"), _rules())
        assert result.action == "parse"
        assert result.parser == "biopython"

    def test_match_fasta(self):
        result = match_file(Path("seq.fasta"), _rules())
        assert result.action == "parse"
        assert result.parser == "biopython"

    def test_match_dotfile_ignored(self):
        result = match_file(Path(".DS_Store"), _rules())
        assert result.action == "ignore"

    def test_match_tmp_ignored(self):
        result = match_file(Path("temp.tmp"), _rules())
        assert result.action == "ignore"

    def test_match_log_logged(self):
        result = match_file(Path("watcher.log"), _rules())
        assert result.action == "log"
        assert result.message == "Log file detected"

    def test_no_match_falls_through(self):
        result = match_file(Path("readme.txt"), _rules())
        assert result.action == "log"
        assert "No rule matched" in result.message

    def test_first_match_wins(self):
        """First matching rule takes priority."""
        rules = [
            WatcherRule(match="*.gb", action="ignore"),
            WatcherRule(match="*.gb", action="parse", parser="biopython"),
        ]
        result = match_file(Path("test.gb"), rules)
        assert result.action == "ignore"

    def test_extracts_preserved(self):
        result = match_file(Path("test.dna"), _rules())
        assert result.extract == ["sequence", "features", "primers", "notes"]

    def test_path_with_directory(self):
        result = match_file(Path("/data/sequences/my_plasmid.gb"), _rules())
        assert result.action == "parse"
        assert result.parser == "biopython"

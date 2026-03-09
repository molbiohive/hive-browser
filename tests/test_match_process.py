"""Tests for BLAST-based variant detection process."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hive.ps.match import MatchProcess, _parse_part_id, _process_hits


# -- _parse_part_id ----------------------------------------------------------


class TestParsePartId:
    def test_valid(self):
        assert _parse_part_id("pid_42_GFP") == 42

    def test_no_prefix(self):
        assert _parse_part_id("sid_5_pUC19") is None

    def test_invalid_number(self):
        assert _parse_part_id("pid_abc_thing") is None

    def test_no_name(self):
        assert _parse_part_id("pid_7") == 7

    def test_plain_name(self):
        assert _parse_part_id("GFP") is None

    def test_empty(self):
        assert _parse_part_id("") is None


# -- _process_hits ------------------------------------------------------------


class TestProcessHits:
    def _hit(self, subject="pid_10_GFP", identity=98.0, alignment_length=100):
        return {
            "subject": subject,
            "identity": identity,
            "alignment_length": alignment_length,
            "mismatches": 2,
            "gaps": 0,
            "q_start": 1,
            "q_end": 100,
            "s_start": 1,
            "s_end": 100,
            "evalue": 1e-50,
            "bitscore": 200.0,
        }

    def test_basic_match(self):
        hits = [self._hit()]
        result = _process_hits(5, 100, hits, 90.0, 80.0)
        assert len(result) == 1
        assert result[0]["pid"] == 10
        assert result[0]["identity"] == 98.0
        assert result[0]["coverage"] == 100.0

    def test_self_match_skipped(self):
        hits = [self._hit(subject="pid_5_GFP")]
        result = _process_hits(5, 100, hits, 90.0, 80.0)
        assert result == []

    def test_below_identity_threshold(self):
        hits = [self._hit(identity=80.0)]
        result = _process_hits(5, 100, hits, 90.0, 80.0)
        assert result == []

    def test_below_coverage_threshold(self):
        hits = [self._hit(alignment_length=50)]
        result = _process_hits(5, 100, hits, 90.0, 80.0)
        assert result == []

    def test_non_part_hit_skipped(self):
        hits = [self._hit(subject="sid_3_pUC19")]
        result = _process_hits(5, 100, hits, 90.0, 80.0)
        assert result == []

    def test_multiple_matches(self):
        hits = [
            self._hit(subject="pid_10_GFP"),
            self._hit(subject="pid_20_eGFP", identity=95.0),
        ]
        result = _process_hits(5, 100, hits, 90.0, 80.0)
        assert len(result) == 2
        pids = {r["pid"] for r in result}
        assert pids == {10, 20}


# -- MatchProcess.run --------------------------------------------------------


class TestMatchProcessRun:
    @pytest.mark.asyncio
    async def test_no_dep_registry(self):
        proc = MatchProcess(MagicMock(), dep_registry=None)
        ctx = MagicMock()
        result = await proc.run(ctx)
        assert "No dep registry" in result

    @pytest.mark.asyncio
    async def test_no_blast_dep(self):
        registry = MagicMock()
        registry.get.return_value = None
        proc = MatchProcess(MagicMock(), dep_registry=registry)
        ctx = MagicMock()
        result = await proc.run(ctx)
        assert "BLAST dep not registered" in result

    @pytest.mark.asyncio
    async def test_no_database(self):
        registry = MagicMock()
        registry.get.return_value = MagicMock()
        proc = MatchProcess(MagicMock(), dep_registry=registry)
        ctx = MagicMock()
        with patch("hive.ps.match.db") as mock_db:
            mock_db.async_session_factory = None
            result = await proc.run(ctx)
        assert "Database unavailable" in result

    @pytest.mark.asyncio
    async def test_empty_db(self):
        """No parts in DB -> 0 scanned."""
        registry = MagicMock()
        blast_dep = AsyncMock()
        registry.get.return_value = blast_dep

        config = MagicMock()
        config.dep_data_dir.return_value = "/tmp/blast_test"

        proc = MatchProcess(config, dep_registry=registry)
        ctx = AsyncMock()

        # Mock DB sessions
        mock_session = AsyncMock()
        # First call: delete annotations
        # Second call: select parts -> empty
        mock_session.execute = AsyncMock(side_effect=[
            MagicMock(),  # delete
            MagicMock(all=lambda: []),  # select parts (empty)
        ])
        mock_session.commit = AsyncMock()
        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("hive.ps.match.db") as mock_db:
            mock_db.async_session_factory = MagicMock(return_value=mock_factory)
            result = await proc.run(ctx)

        assert "0 parts scanned" in result

    @pytest.mark.asyncio
    async def test_scan_with_match(self):
        """One part with one BLAST hit -> 1 variant found."""
        registry = MagicMock()
        blast_dep = AsyncMock()
        blast_dep.run_search = AsyncMock(return_value={
            "hits": [{
                "subject": "pid_20_eGFP",
                "identity": 97.5,
                "alignment_length": 100,
                "mismatches": 2,
                "gaps": 0,
                "q_start": 1,
                "q_end": 100,
                "s_start": 1,
                "s_end": 100,
                "evalue": 1e-50,
                "bitscore": 200.0,
            }],
            "subject_names": {"pid_20_eGFP"},
        })
        registry.get.return_value = blast_dep

        config = MagicMock()
        config.dep_data_dir.return_value = "/tmp/blast_test"

        proc = MatchProcess(config, dep_registry=registry)
        ctx = AsyncMock()

        call_count = [0]
        committed_annotations = []

        async def fake_execute(stmt):
            call_count[0] += 1
            if call_count[0] <= 1:
                # delete annotations
                return MagicMock()
            elif call_count[0] == 2:
                # commit after delete
                return MagicMock()
            elif call_count[0] == 3:
                # select parts: one part (pid=10, seq=100bp DNA)
                return MagicMock(all=lambda: [(10, "ATGC" * 25, "DNA")])
            elif call_count[0] == 5:
                # second batch select: empty
                return MagicMock(all=lambda: [])
            return MagicMock()

        class FakeSession:
            def __init__(self):
                self._call = 0

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def execute(self, stmt):
                return await fake_execute(stmt)

            async def commit(self):
                pass

            def add(self, obj):
                committed_annotations.append(obj)

        session_count = [0]

        def make_session():
            s = FakeSession()
            return s

        with patch("hive.ps.match.db") as mock_db:
            mock_db.async_session_factory = make_session
            result = await proc.run(ctx)

        assert "1 parts scanned" in result
        assert "1 variants found" in result
        assert len(committed_annotations) == 1
        ann = committed_annotations[0]
        assert ann.key == "blast_similar"
        assert "pid:20" in ann.value
        assert ann.source == "blast"


# -- _sanitize_fasta_name (in deps/blast.py) ---------------------------------


class TestSanitizeFastaName:
    def test_basic(self):
        from hive.deps.blast import _sanitize_fasta_name
        assert _sanitize_fasta_name("pUC19") == "pUC19"

    def test_spaces(self):
        from hive.deps.blast import _sanitize_fasta_name
        assert _sanitize_fasta_name("my plasmid") == "my_plasmid"

    def test_unicode_stripped(self):
        from hive.deps.blast import _sanitize_fasta_name
        assert _sanitize_fasta_name("p\u00dcC19") == "pC19"

    def test_all_unicode(self):
        from hive.deps.blast import _sanitize_fasta_name
        assert _sanitize_fasta_name("\u00fc\u00e4\u00f6") == "unnamed"

    def test_empty(self):
        from hive.deps.blast import _sanitize_fasta_name
        assert _sanitize_fasta_name("") == "unnamed"

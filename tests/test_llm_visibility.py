"""Test: workspace storage, descriptors, widget data, and format_result.

Verifies:
1. Widget gets the FULL result dict (no field loss)
2. store_result() correctly breaks out sub-entries
3. Workspace descriptors inline scalars and type-hint complex values
4. format_result() (chain summary) contains essential info
"""

import pytest

from hive.sandbox.workspace import Workspace
from hive.tools.router import _tool_response

# ── Helpers ──


def widget_gets(tool_name: str, result: dict) -> dict:
    """Simulate what the frontend widget receives."""
    resp = _tool_response(tool_name, result, {}, "")
    return resp["data"]


# ── Synthetic Results ──

SEARCH_RESULT = {
    "results": [
        {
            "sid": 1,
            "name": "pUC19",
            "size_bp": 2686,
            "topology": "circular",
            "features": ["AmpR", "lacZ"],
            "tags": ["plasmid"],
            "file_path": "/data/pUC19.dna",
            "score": 0.95,
        },
        {
            "sid": 2,
            "name": "pBR322",
            "size_bp": 4361,
            "topology": "circular",
            "features": ["AmpR", "TetR"],
            "tags": [],
            "file_path": "/data/pBR322.dna",
            "score": 0.88,
        },
    ],
    "total": 2,
    "parts": [
        {
            "pid": 10,
            "names": ["AmpR"],
            "molecule": "dna",
            "length": 861,
            "instance_count": 5,
            "types": ["CDS"],
            "score": 0.92,
        },
    ],
    "parts_total": 1,
    "query": "ampicillin",
}

PROFILE_RESULT = {
    "sequence": {
        "sid": 1,
        "name": "pUC19",
        "size_bp": 2686,
        "topology": "circular",
        "molecule": "dna",
        "description": "Cloning vector",
        "meta": {"organism": "synthetic"},
        "sequence_data": "ATCG" * 500,
    },
    "features": [
        {
            "pid": 10,
            "name": "AmpR",
            "type": "CDS",
            "start": 100,
            "end": 960,
            "strand": 1,
            "qualifiers": {"product": "ampicillin resistance"},
        },
    ],
    "primers": [
        {
            "pid": 20,
            "name": "M13F",
            "start": 400,
            "end": 417,
            "strand": 1,
            "length": 17,
            "sequence": "GTAAAACGACGGCCAGT",
            "source": "file",
        },
    ],
    "cut_sites": [
        {
            "enzyme": "EcoRI",
            "position": 396,
            "end": 402,
            "strand": 1,
            "cutPosition": 397,
            "complementCutPosition": 401,
            "overhang": "5'",
        },
    ],
    "file": {"path": "/data/pUC19.dna", "format": "sgff", "size": 8192, "indexed_at": "2025-01-01"},
}

BLAST_RESULT = {
    "hits": [
        {
            "subject": "pUC19 complete vector",
            "identity": 99.5,
            "alignment_length": 2686,
            "mismatches": 13,
            "gaps": 0,
            "q_start": 1,
            "q_end": 2686,
            "s_start": 1,
            "s_end": 2686,
            "evalue": 0.0,
            "bitscore": 4962.0,
            "sid": 1,
            "pid": None,
            "file_path": "/data/pUC19.dna",
        },
        {
            "subject": "pBR322 origin region",
            "identity": 85.2,
            "alignment_length": 600,
            "mismatches": 89,
            "gaps": 2,
            "q_start": 1500,
            "q_end": 2100,
            "s_start": 2000,
            "s_end": 2600,
            "evalue": 1e-120,
            "bitscore": 450.0,
            "sid": 2,
            "pid": None,
            "file_path": "/data/pBR322.dna",
        },
    ],
    "total": 2,
    "query_length": 2686,
    "program": "blastn",
}

ALIGN_RESULT = {
    "aligned": ">seq1\nATCGATCG--ATCG\n>seq2\nATCGATCGATATCG\n",
    "count": 2,
}

EXTRACT_RESULT = {
    "sequence": "ATCGATCG" * 50,
    "name": "AmpR",
    "pid": 10,
    "source": "pUC19",
    "start": 100,
    "end": 960,
    "strand": 1,
    "length": 861,
}

DIGEST_RESULT = {
    "reactions": [
        {
            "name": "EcoRI",
            "enzymes": [{"name": "EcoRI", "sites": [396]}],
            "fragments": [2686],
            "total_cuts": 1,
        },
    ],
    "sequence_length": 2686,
    "circular": True,
    "gel_data": {
        "lanes": [
            {
                "label": "EcoRI",
                "bands": [{"position": 0.5, "intensity": 1.0, "size": 2686, "name": ""}],
            }
        ],
        "gelType": "agarose",
        "stain": "ethidium",
    },
}

SITES_RESULT = {
    "cutters": [
        {"name": "EcoRI", "num_cuts": 1, "positions": [396]},
        {"name": "BamHI", "num_cuts": 2, "positions": [100, 2000]},
    ],
    "cutters_found": 2,
    "total_enzymes_scanned": 754,
}

PARTS_PID_RESULT = {
    "part": {
        "pid": 10,
        "names": ["AmpR"],
        "molecule": "dna",
        "length": 861,
        "sequence": "ATCG" * 200,
        "sequence_hash": "abc123",
    },
    "instances": [
        {
            "sid": 1,
            "sequence_name": "pUC19",
            "annotation_type": "CDS",
            "start": 100,
            "end": 960,
            "strand": 1,
            "file_path": "/data/pUC19.dna",
        },
    ],
    "instances_count": 1,
    "annotations": [{"key": "product", "value": "ampicillin resistance", "source": "genbank"}],
    "libraries": [{"id": 1, "name": "default"}],
    "relatives": [],
}

PARTS_SID_RESULT = {
    "parts": [
        {
            "pid": 10,
            "name": "AmpR",
            "type": "CDS",
            "start": 100,
            "end": 960,
            "strand": 1,
            "length": 861,
        },
        {
            "pid": 20,
            "name": "lacZ",
            "type": "CDS",
            "start": 1200,
            "end": 2400,
            "strand": -1,
            "length": 1200,
        },
    ],
    "total": 2,
    "sequence_name": "pUC19",
}

REVCOMP_RESULT = {"sequence": "ATCG" * 200, "length": 800}

TRANSLATE_RESULT = {
    "protein": "MKLIV" * 50,
    "nucleotide_length": 750,
    "protein_length": 250,
    "stop_codons": 1,
    "complete": True,
    "codon_table": 1,
}

TRANSCRIBE_RESULT = {"rna": "AUCG" * 200, "length": 800}

GC_RESULT = {
    "gc_percent": 52.3,
    "at_percent": 47.7,
    "length": 2686,
    "g": 702,
    "c": 703,
    "a": 640,
    "t": 641,
}


# ── Tests ──


class TestWidgetGetsFullData:
    """Widget (frontend) must receive the complete, unmodified result dict."""

    @pytest.mark.parametrize(
        "tool_name,result",
        [
            ("search", SEARCH_RESULT),
            ("profile", PROFILE_RESULT),
            ("blast", BLAST_RESULT),
            ("align", ALIGN_RESULT),
            ("extract", EXTRACT_RESULT),
            ("digest", DIGEST_RESULT),
            ("sites", SITES_RESULT),
            ("parts", PARTS_PID_RESULT),
            ("parts", PARTS_SID_RESULT),
            ("revcomp", REVCOMP_RESULT),
            ("translate", TRANSLATE_RESULT),
            ("transcribe", TRANSCRIBE_RESULT),
            ("gc", GC_RESULT),
        ],
    )
    def test_widget_receives_exact_result(self, tool_name, result):
        """_tool_response passes the full result dict to data field untouched."""
        data = widget_gets(tool_name, result)
        assert data is result  # same object, no copy/filter


class TestWorkspaceStorage:
    """store_result() breaks results into typed workspace entries."""

    def test_gc_all_scalars(self):
        """All-scalar result: only _result entry (no sub-entries)."""
        ws = Workspace()
        ws.store_result(GC_RESULT, "gc")
        assert len(ws) == 1  # just _result
        assert ws.get("r0") is GC_RESULT

    def test_search_breaks_out_lists(self):
        """Lists are broken out as separate entries."""
        ws = Workspace()
        ws.store_result(SEARCH_RESULT, "search")
        # _result + results + parts = 3
        assert len(ws) >= 3
        assert ws.get("r0") is SEARCH_RESULT
        # results list
        assert ws.get("r1") is SEARCH_RESULT["results"]
        # parts list
        assert ws.get("r2") is SEARCH_RESULT["parts"]

    def test_profile_breaks_out_complex(self):
        """Profile: sequence dict (>2 keys), features list, primers list, cut_sites list, file dict."""
        ws = Workspace()
        ws.store_result(PROFILE_RESULT, "profile")
        # _result + sequence + features + primers + cut_sites + file = 6
        assert len(ws) == 6
        # Verify references are shared (not copied)
        assert ws.get("r1") is PROFILE_RESULT["sequence"]
        assert ws.get("r2") is PROFILE_RESULT["features"]

    def test_extract_breaks_out_long_string(self):
        """Long strings (>=200 chars) are broken out."""
        ws = Workspace()
        ws.store_result(EXTRACT_RESULT, "extract")
        # _result + sequence (400 chars) = 2
        assert len(ws) == 2
        assert ws.get("r1") is EXTRACT_RESULT["sequence"]

    def test_error_result_bypasses(self):
        """Error fields are not stored."""
        ws = Workspace()
        ws.store_result({"error": "not found", "details": [1, 2]}, "search")
        # _result + details list = 2  (error key skipped)
        assert len(ws) == 2

    def test_no_memory_duplication(self):
        """Sub-entries reference same objects as _result (no copies)."""
        ws = Workspace()
        ws.store_result(SEARCH_RESULT, "search")
        full = ws.get("r0")
        results_list = ws.get("r1")
        assert full["results"] is results_list


class TestWorkspaceDescriptor:
    """Workspace descriptors inline scalars and type-hint complex values."""

    def test_gc_descriptor_shows_scalars(self):
        """All-scalar dict shows values inline."""
        ws = Workspace()
        ws.store_result(GC_RESULT, "gc")
        desc = ws.describe("r0")
        assert "gc_percent=52.3" in desc
        assert "length=2686" in desc
        assert "gc" in desc  # tool name

    def test_search_descriptor_shows_counts_and_types(self):
        """Mixed dict: scalar values inline, lists as type hints."""
        ws = Workspace()
        ws.store_result(SEARCH_RESULT, "search")
        desc = ws.describe("r0")
        assert "total=2" in desc
        assert "results=list(2)" in desc
        assert "query=ampicillin" in desc

    def test_list_descriptor_shows_columns(self):
        """List[dict] entries show row count and column names."""
        ws = Workspace()
        ws.store_result(SEARCH_RESULT, "search")
        desc = ws.describe("r1")  # results list
        assert "list[dict]" in desc
        assert "2 rows" in desc
        assert "sid" in desc

    def test_long_string_shows_char_count(self):
        """Long string entries show character count."""
        ws = Workspace()
        ws.store_result(EXTRACT_RESULT, "extract")
        desc = ws.describe("r1")  # sequence string
        assert "str" in desc
        assert "400 chars" in desc

    def test_dict_descriptor_shows_nested_types(self):
        """Nested dict shows scalar values inline + type hints."""
        ws = Workspace()
        ws.store_result(PROFILE_RESULT, "profile")
        # r1 is the sequence dict
        desc = ws.describe("r1")
        assert "sid=1" in desc
        assert "name=pUC19" in desc
        assert "size_bp=2686" in desc


class TestFormatResult:
    """format_result() produces human-readable one-liners for the chain UI."""

    def test_search_format(self):
        from hive.tools.search import SearchTool

        tool = SearchTool.__new__(SearchTool)
        text = tool.format_result(SEARCH_RESULT)
        assert "2 sequence" in text
        assert "1 part" in text
        assert "ampicillin" in text

    def test_blast_format(self):
        from hive.tools.blast import BlastTool

        tool = BlastTool.__new__(BlastTool)
        text = tool.format_result(BLAST_RESULT)
        assert "2" in text
        assert "blastn" in text

    def test_profile_format(self):
        from hive.tools.profile import ProfileTool

        tool = ProfileTool.__new__(ProfileTool)
        text = tool.format_result(PROFILE_RESULT)
        assert "pUC19" in text
        assert "2686 bp" in text

    def test_digest_format(self):
        from hive.tools.digest import DigestTool

        tool = DigestTool.__new__(DigestTool)
        text = tool.format_result(DIGEST_RESULT)
        assert "EcoRI" in text
        assert "1 cut" in text

    def test_gc_format(self):
        from hive.tools.gc import GCTool

        tool = GCTool.__new__(GCTool)
        text = tool.format_result(GC_RESULT)
        assert "52.3" in text
        assert "2686" in text

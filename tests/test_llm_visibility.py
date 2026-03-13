"""Exhaustive test: LLM context visibility vs widget (user viewport) data.

For every tool, verifies:
1. Widget gets the FULL result dict (no field loss)
2. LLM summary preserves critical fields (IDs, counts, metadata)
3. Long strings are truncated (not redacted, just length-limited)
4. format_result() (chain summary) contains essential info

No redaction -- local models get all data. The only transformation is
compaction: lists are sampled, long strings truncated to 100 chars.
"""

import json

import pytest

from hive.tools.router import _summarize_for_llm, _tool_response


# ── Helpers ──


def llm_sees(result: dict) -> dict:
    """Run result through the standard LLM summarizer, return parsed JSON."""
    text = _summarize_for_llm(result)
    return json.loads(text)


def widget_gets(tool_name: str, result: dict) -> dict:
    """Simulate what the frontend widget receives."""
    resp = _tool_response(tool_name, result, {}, "")
    return resp["data"]


# ── Synthetic Results ──

SEARCH_RESULT = {
    "results": [
        {"sid": 1, "name": "pUC19", "size_bp": 2686, "topology": "circular",
         "features": ["AmpR", "lacZ"], "tags": ["plasmid"], "file_path": "/data/pUC19.dna", "score": 0.95},
        {"sid": 2, "name": "pBR322", "size_bp": 4361, "topology": "circular",
         "features": ["AmpR", "TetR"], "tags": [], "file_path": "/data/pBR322.dna", "score": 0.88},
    ],
    "total": 2,
    "parts": [
        {"pid": 10, "names": ["AmpR"], "molecule": "dna", "length": 861,
         "instance_count": 5, "types": ["CDS"], "score": 0.92},
    ],
    "parts_total": 1,
    "query": "ampicillin",
}

PROFILE_RESULT = {
    "sequence": {
        "sid": 1, "name": "pUC19", "size_bp": 2686, "topology": "circular",
        "molecule": "dna", "description": "Cloning vector",
        "meta": {"organism": "synthetic"}, "sequence_data": "ATCG" * 500,
    },
    "features": [
        {"pid": 10, "name": "AmpR", "type": "CDS", "start": 100, "end": 960,
         "strand": 1, "qualifiers": {"product": "ampicillin resistance"}},
    ],
    "primers": [
        {"pid": 20, "name": "M13F", "start": 400, "end": 417, "strand": 1,
         "length": 17, "sequence": "GTAAAACGACGGCCAGT", "source": "file"},
    ],
    "cut_sites": [
        {"enzyme": "EcoRI", "position": 396, "end": 402, "strand": 1,
         "cutPosition": 397, "complementCutPosition": 401, "overhang": "5'"},
    ],
    "file": {"path": "/data/pUC19.dna", "format": "sgff", "size": 8192, "indexed_at": "2025-01-01"},
}

BLAST_RESULT = {
    "hits": [
        {"subject": "pUC19 complete vector", "identity": 99.5, "alignment_length": 2686,
         "mismatches": 13, "gaps": 0, "q_start": 1, "q_end": 2686,
         "s_start": 1, "s_end": 2686, "evalue": 0.0, "bitscore": 4962.0,
         "sid": 1, "pid": None, "file_path": "/data/pUC19.dna"},
        {"subject": "pBR322 origin region", "identity": 85.2, "alignment_length": 600,
         "mismatches": 89, "gaps": 2, "q_start": 1500, "q_end": 2100,
         "s_start": 2000, "s_end": 2600, "evalue": 1e-120, "bitscore": 450.0,
         "sid": 2, "pid": None, "file_path": "/data/pBR322.dna"},
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
        {"name": "EcoRI", "enzymes": [{"name": "EcoRI", "sites": [396]}],
         "fragments": [2686], "total_cuts": 1},
    ],
    "sequence_length": 2686,
    "circular": True,
    "gel_data": {
        "lanes": [{"label": "EcoRI", "bands": [{"position": 0.5, "intensity": 1.0, "size": 2686, "name": ""}]}],
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
        "pid": 10, "names": ["AmpR"], "molecule": "dna",
        "length": 861, "sequence": "ATCG" * 200, "sequence_hash": "abc123",
    },
    "instances": [
        {"sid": 1, "sequence_name": "pUC19", "annotation_type": "CDS",
         "start": 100, "end": 960, "strand": 1, "file_path": "/data/pUC19.dna"},
    ],
    "instances_count": 1,
    "annotations": [{"key": "product", "value": "ampicillin resistance", "source": "genbank"}],
    "libraries": [{"id": 1, "name": "default"}],
    "relatives": [],
}

PARTS_SID_RESULT = {
    "parts": [
        {"pid": 10, "name": "AmpR", "type": "CDS", "start": 100, "end": 960, "strand": 1, "length": 861},
        {"pid": 20, "name": "lacZ", "type": "CDS", "start": 1200, "end": 2400, "strand": -1, "length": 1200},
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

GC_RESULT = {"gc_percent": 52.3, "at_percent": 47.7, "length": 2686, "g": 702, "c": 703, "a": 640, "t": 641}


# ── Tests ──


class TestWidgetGetsFullData:
    """Widget (frontend) must receive the complete, unmodified result dict."""

    @pytest.mark.parametrize("tool_name,result", [
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
    ])
    def test_widget_receives_exact_result(self, tool_name, result):
        """_tool_response passes the full result dict to data field untouched."""
        data = widget_gets(tool_name, result)
        assert data is result  # same object, no copy/filter


class TestLLMSeesIDs:
    """LLM must always have access to SID/PID/ID fields for tool chaining."""

    def test_search_sids_visible(self):
        s = llm_sees(SEARCH_RESULT)
        sample = s["results_sample"]
        assert all("sid" in item for item in sample)

    def test_search_parts_pids_visible(self):
        s = llm_sees(SEARCH_RESULT)
        sample = s["parts_sample"]
        assert all("pid" in item for item in sample)

    def test_blast_sids_visible(self):
        s = llm_sees(BLAST_RESULT)
        sample = s["hits_sample"]
        assert all("sid" in item for item in sample)

    def test_parts_pid_mode_pid_visible(self):
        s = llm_sees(PARTS_PID_RESULT)
        assert "part" in s
        assert s["part"]["pid"] == 10

    def test_parts_sid_mode_pids_visible(self):
        s = llm_sees(PARTS_SID_RESULT)
        sample = s["parts_sample"]
        assert all("pid" in item for item in sample)

    def test_profile_sid_visible(self):
        """Profile 'sequence' is a nested dict -- shallow scalars extracted."""
        s = llm_sees(PROFILE_RESULT)
        assert s["sequence"]["sid"] == 1

    def test_extract_pid_visible(self):
        s = llm_sees(EXTRACT_RESULT)
        assert s["pid"] == 10


class TestLLMSeesMetadata:
    """LLM must see counts, scores, and metadata for informed decisions."""

    def test_search_total_and_query(self):
        s = llm_sees(SEARCH_RESULT)
        assert s["total"] == 2
        assert s["parts_total"] == 1
        assert s["query"] == "ampicillin"

    def test_search_scores_visible(self):
        s = llm_sees(SEARCH_RESULT)
        sample = s["results_sample"]
        assert all("score" in item for item in sample)

    def test_search_size_visible(self):
        s = llm_sees(SEARCH_RESULT)
        sample = s["results_sample"]
        assert all("size_bp" in item for item in sample)

    def test_search_names_visible(self):
        s = llm_sees(SEARCH_RESULT)
        sample = s["results_sample"]
        assert all("name" in item for item in sample)

    def test_search_file_paths_visible(self):
        s = llm_sees(SEARCH_RESULT)
        sample = s["results_sample"]
        assert all("file_path" in item for item in sample)

    def test_blast_alignment_metrics(self):
        s = llm_sees(BLAST_RESULT)
        assert s["total"] == 2
        assert s["query_length"] == 2686
        assert s["program"] == "blastn"
        hit = s["hits_sample"][0]
        assert "identity" in hit
        assert "alignment_length" in hit
        assert "evalue" in hit
        assert "bitscore" in hit

    def test_blast_subject_visible(self):
        s = llm_sees(BLAST_RESULT)
        hit = s["hits_sample"][0]
        assert "subject" in hit

    def test_blast_file_paths_visible(self):
        s = llm_sees(BLAST_RESULT)
        hit = s["hits_sample"][0]
        assert "file_path" in hit

    def test_profile_sequence_metadata(self):
        """Profile sequence dict: shallow scalars extracted (no redaction)."""
        s = llm_sees(PROFILE_RESULT)
        seq = s["sequence"]
        assert seq["sid"] == 1
        assert seq["name"] == "pUC19"
        assert seq["size_bp"] == 2686
        assert seq["topology"] == "circular"
        assert seq["molecule"] == "dna"
        assert seq["description"] == "Cloning vector"

    def test_profile_file_metadata(self):
        s = llm_sees(PROFILE_RESULT)
        f = s["file"]
        assert f["path"] == "/data/pUC19.dna"
        assert f["format"] == "sgff"
        assert f["size"] == 8192

    def test_profile_feature_details(self):
        s = llm_sees(PROFILE_RESULT)
        sample = s["features_sample"]
        feat = sample[0]
        assert feat["name"] == "AmpR"
        assert feat["type"] == "CDS"
        assert feat["start"] == 100
        assert feat["end"] == 960

    def test_profile_primer_details(self):
        s = llm_sees(PROFILE_RESULT)
        sample = s["primers_sample"]
        primer = sample[0]
        assert primer["name"] == "M13F"
        assert primer["start"] == 400
        assert primer["sequence"] == "GTAAAACGACGGCCAGT"

    def test_profile_cut_site_details(self):
        s = llm_sees(PROFILE_RESULT)
        sample = s["cut_sites_sample"]
        cs = sample[0]
        assert cs["enzyme"] == "EcoRI"
        assert cs["position"] == 396

    def test_digest_reactions(self):
        s = llm_sees(DIGEST_RESULT)
        assert s["sequence_length"] == 2686
        assert s["circular"] is True
        sample = s["reactions_sample"]
        rxn = sample[0]
        assert rxn["name"] == "EcoRI"
        assert rxn["total_cuts"] == 1

    def test_sites_cutters(self):
        s = llm_sees(SITES_RESULT)
        assert s["cutters_found"] == 2
        assert s["total_enzymes_scanned"] == 754
        sample = s["cutters_sample"]
        assert any(c["name"] == "EcoRI" for c in sample)

    def test_gc_all_metrics(self):
        s = llm_sees(GC_RESULT)
        assert s["gc_percent"] == 52.3
        assert s["at_percent"] == 47.7
        assert s["length"] == 2686
        assert s["g"] == 702
        assert s["c"] == 703

    def test_translate_metadata(self):
        s = llm_sees(TRANSLATE_RESULT)
        assert s["nucleotide_length"] == 750
        assert s["protein_length"] == 250
        assert s["stop_codons"] == 1
        assert s["complete"] is True
        assert s["codon_table"] == 1

    def test_extract_metadata(self):
        s = llm_sees(EXTRACT_RESULT)
        assert s["name"] == "AmpR"
        assert s["source"] == "pUC19"
        assert s["start"] == 100
        assert s["end"] == 960
        assert s["length"] == 861

    def test_align_count(self):
        s = llm_sees(ALIGN_RESULT)
        assert s["count"] == 2

    def test_revcomp_length(self):
        s = llm_sees(REVCOMP_RESULT)
        assert s["length"] == 800

    def test_transcribe_length(self):
        s = llm_sees(TRANSCRIBE_RESULT)
        assert s["length"] == 800

    def test_parts_instances_file_paths_visible(self):
        s = llm_sees(PARTS_PID_RESULT)
        for item in s["instances_sample"]:
            assert "file_path" in item


class TestLLMStringTruncation:
    """Long strings are truncated at 100 chars + '...' (threshold: 200 chars)."""

    def test_short_string_preserved(self):
        result = {"description": "Short text"}
        s = llm_sees(result)
        assert s["description"] == "Short text"

    def test_long_string_truncated(self):
        result = {"description": "A" * 300}
        s = llm_sees(result)
        assert s["description"] == "A" * 100 + "..."

    def test_medium_string_preserved(self):
        """Strings under 200 chars are kept in full."""
        result = {"description": "B" * 199}
        s = llm_sees(result)
        assert s["description"] == "B" * 199

    def test_sequence_truncated(self):
        """Sequences (long strings) are truncated, not hidden."""
        s = llm_sees(EXTRACT_RESULT)
        assert "sequence" in s
        assert s["sequence"].endswith("...")

    def test_protein_truncated(self):
        s = llm_sees(TRANSLATE_RESULT)
        assert "protein" in s
        assert s["protein"].endswith("...")
        assert len(s["protein"]) <= 104  # 100 + "..."

    def test_rna_truncated(self):
        s = llm_sees(TRANSCRIBE_RESULT)
        assert "rna" in s
        assert s["rna"].endswith("...")

    def test_revcomp_sequence_truncated(self):
        s = llm_sees(REVCOMP_RESULT)
        assert "sequence" in s
        assert s["sequence"].endswith("...")

    def test_nested_long_strings_excluded_from_shallow_dict(self):
        """Dict extraction skips strings >= 200 chars."""
        s = llm_sees(PROFILE_RESULT)
        # sequence_data is 2000 chars, excluded from shallow extraction
        assert "sequence_data" not in s.get("sequence", {})


class TestLLMListSampling:
    """Large result lists are sampled but all IDs preserved.

    max_items = max(5, token_limit // 50).  Default token_limit=1000 -> max_items=20.
    """

    def test_default_max_items_is_20(self):
        """With default token_limit=1000, max_items = max(5, 1000//50) = 20."""
        result = {
            "results": [{"sid": i, "name": f"seq{i}"} for i in range(20)],
        }
        s = llm_sees(result)
        assert s["results_count"] == 20
        assert len(s["results_sample"]) == 20

    def test_large_list_sampled(self):
        """Lists exceeding max_items get truncated and IDs collected."""
        result = {
            "results": [{"sid": i, "name": f"seq{i}"} for i in range(50)],
        }
        s = llm_sees(result)
        assert s["results_count"] == 50
        assert len(s["results_sample"]) == 20

    def test_all_sids_preserved(self):
        result = {
            "results": [{"sid": i, "name": f"seq{i}"} for i in range(50)],
        }
        s = llm_sees(result)
        assert s["all_results_sids"] == list(range(50))

    def test_all_pids_preserved(self):
        result = {
            "parts": [{"pid": i, "name": f"part{i}"} for i in range(50)],
        }
        s = llm_sees(result)
        assert s["all_parts_pids"] == list(range(50))

    def test_small_list_not_sampled(self):
        result = {
            "results": [{"sid": i} for i in range(3)],
        }
        s = llm_sees(result)
        assert s["results_count"] == 3
        assert len(s["results_sample"]) == 3
        assert "all_results_sids" not in s

    def test_custom_token_limit_changes_max_items(self):
        """Lower token_limit reduces max_items: 250 -> max(5, 250//50) = 5."""
        result = {
            "results": [{"sid": i, "name": f"seq{i}"} for i in range(20)],
        }
        text = _summarize_for_llm(result, token_limit=250)
        s = json.loads(text)
        assert s["results_count"] == 20
        assert len(s["results_sample"]) == 5
        assert s["all_results_sids"] == list(range(20))



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
